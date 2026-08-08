import json

import pytest

from aeonisk.multiagent.llm_logger import ReplayStructuredProvider
from aeonisk.multiagent.replay import ReplaySession
from aeonisk.multiagent.session import SelfPlayingSession


class _Response:
    class _Content:
        text = '{"value": 7}'

    content = [_Content()]


class _Client:
    class _Messages:
        def create(self, **kwargs):
            return _Response()

    messages = _Messages()


class _Result:
    value: int

    @classmethod
    def model_validate(cls, payload):
        instance = cls()
        instance.value = payload['value']
        return instance


@pytest.mark.asyncio
async def test_replay_structured_provider_parses_cached_json():
    result = await ReplayStructuredProvider(_Client()).generate_structured(
        prompt='ignored', result_type=_Result
    )
    assert result.value == 7


def test_replay_aliases_generated_enemy_ids_to_cached_ids():
    session = SelfPlayingSession.__new__(SelfPlayingSession)
    session.llm_cache = {
        ('enemy_source_b', 0): {'response': '{}'},
        ('enemy_source_a', 0): {'response': '{}'},
    }
    session.continue_from_round = None
    session.hybrid_clients = []
    session._replay_agent_aliases = {}

    first = session._get_replay_client('enemy_runtime_1')
    second = session._get_replay_client('enemy_runtime_2')

    assert first.agent_id == 'enemy_source_a'
    assert second.agent_id == 'enemy_source_b'


def test_replay_validation_requires_player_cache(tmp_path):
    path = tmp_path / 'session.jsonl'
    events = [
        {
            'event_type': 'session_start',
            'session': 'test-session',
            'random_seed': 1,
            'config': {
                'party_size': 1,
                'agents': {
                    'dm': {'llm': {'provider': 'batch_proxy'}},
                    'players': [{'llm': {'provider': 'batch_proxy'}}],
                },
            },
        },
        {'event_type': 'scenario'},
        {'event_type': 'round_start'},
        {
            'event_type': 'llm_call',
            'agent_id': 'dm_01',
            'call_sequence': 0,
            'prompt': [],
            'response': '{}',
            'model': 'test',
            'temperature': 0,
        },
    ]
    path.write_text('\n'.join(json.dumps(event) for event in events))

    replay = ReplaySession(str(path))
    replay.load_log()
    validation = replay.validate_completeness()

    assert not validation['can_replay']
    assert any('player_01' in issue for issue in validation['issues'])
    assert validation['warnings'] == [
        'batch_proxy configuration will be bypassed for cached replay clients'
    ]
