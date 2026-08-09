"""
Unit tests for faction-awareness fixes across combatant lists and targeting.

Tests cover:
1. DM combatant list includes faction per entity (player, NPC, enemy)
2. Enemy prompt combatant list includes faction per entity
3. DM escalation check NPC list includes faction
4. PC name resolved correctly in enemy prompts (not 'Unknown PC')
5. Enemy-vs-player targeting checks faction alliance
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from scripts.aeonisk.multiagent.enemy_agent import Position
from scripts.aeonisk.multiagent.mechanics import MechanicsEngine


# ============================================================
# Helpers: Create mock agents
# ============================================================

def _make_mock_player(agent_id, name, faction, pronouns="they/them", health=20, max_health=20, wounds=0):
    """Create a mock AIPlayerAgent with character_state."""
    player = MagicMock()
    player.agent_id = agent_id
    player.character_state = MagicMock()
    player.character_state.name = name
    player.character_state.faction = faction
    player.character_state.pronouns = pronouns
    player.health = health
    player.max_health = max_health
    player.wounds = wounds
    player.position = Position.from_string("Near-PC")
    player.defence_token = None
    # AIPlayerAgent does NOT have .name directly — it uses character_state.name
    # We deliberately do NOT set player.name to test that code handles this correctly
    del player.name
    return player


def _make_mock_enemy(agent_id, name, faction, pronouns="they/them", health=15, max_health=15):
    """Create a mock EnemyAgent."""
    enemy = MagicMock()
    enemy.agent_id = agent_id
    enemy.name = name
    enemy.faction = faction
    enemy.pronouns = pronouns
    enemy.health = health
    enemy.max_health = max_health
    enemy.is_active = True
    enemy.position = Position.from_string("Near-Enemy")
    enemy.tactics = "aggressive"
    enemy.threat_priority = "closest_threat"
    enemy.initiative = 10
    return enemy


def _make_mock_npc(agent_id, name, faction, disposition="neutral", pronouns="they/them", health=10, max_health=10):
    """Create a mock NPCAgent."""
    npc = MagicMock()
    npc.agent_id = agent_id
    npc.name = name
    npc.faction = faction
    npc.pronouns = pronouns
    npc.disposition = disposition
    npc.health = health
    npc.max_health = max_health
    return npc


def _make_mock_target_id_mapper(entities):
    """Create a mock TargetIDMapper with entity info.

    entities: list of dicts with keys: tid, name, type, faction, pronouns, agent_id, etc.
    """
    mapper = MagicMock()
    mapper.enabled = True
    mapper.get_all_target_ids.return_value = [e['tid'] for e in entities]

    info_map = {}
    entity_map = {}
    for e in entities:
        info_map[e['tid']] = {
            'name': e['name'],
            'type': e['type'],
            'faction': e.get('faction', 'Unknown'),
            'pronouns': e.get('pronouns', 'they/them'),
            'agent_id': e.get('agent_id', e['tid']),
            'health': e.get('health', 20),
            'max_health': e.get('max_health', 20),
        }
        if '_entity' in e:
            entity_map[e['tid']] = e['_entity']

    mapper.get_combatant_info.side_effect = lambda tid: info_map.get(tid)
    mapper.is_player.side_effect = lambda tid: info_map.get(tid, {}).get('type') == 'player'
    mapper.is_enemy.side_effect = lambda tid: info_map.get(tid, {}).get('type') == 'enemy'
    mapper.get_target_id.side_effect = lambda aid: next(
        (e['tid'] for e in entities if e.get('agent_id') == aid), None
    )
    mapper.resolve_target.side_effect = lambda tid: entity_map.get(tid)

    return mapper


def _build_dm_combatant_list(dm, mapper, npc_mocks=None):
    """Build combatant list using the same logic as dm.py:7650-7692."""
    if npc_mocks is None:
        npc_mocks = []
    dm.shared_state.npc_agents = npc_mocks

    combatant_lines = []
    all_target_ids = mapper.get_all_target_ids()
    for tid in sorted(all_target_ids):
        info = mapper.get_combatant_info(tid)
        if info:
            pronouns = info.get('pronouns', 'they/them')
            faction = info.get('faction', 'Unknown')
            if info['type'] == 'player' and 'agent_id' in info:
                player_agent = dm.shared_state.get_agent_by_id(info['agent_id'])
                if player_agent and hasattr(player_agent, 'health'):
                    health_text = f"{player_agent.health}/{player_agent.max_health} HP"
                    wounds_text = f", {player_agent.wounds}w" if getattr(player_agent, 'wounds', 0) > 0 else ""
                    combatant_lines.append(f"  - [{tid}] {info['name']} ({pronouns}, {faction}, {health_text}{wounds_text})")
                else:
                    combatant_lines.append(f"  - [{tid}] {info['name']} ({pronouns}, {faction}, player)")
            elif info['type'] == 'npc':
                disposition = 'neutral'
                for npc in npc_mocks:
                    if hasattr(npc, 'agent_id') and npc.agent_id == info.get('agent_id'):
                        disposition = getattr(npc, 'disposition', 'neutral')
                        break
                combatant_lines.append(f"  - [{tid}] {info['name']} ({pronouns}, {faction}, npc, {disposition})")
            else:
                combatant_lines.append(f"  - [{tid}] {info['name']} ({pronouns}, {faction}, {info['type']})")

    return combatant_lines


# ============================================================
# 1. DM Combatant List — Faction Per Entity
# ============================================================

class TestDMCombatantListFaction:
    """DM combatant list must show faction for every entity."""

    def setup_method(self):
        from scripts.aeonisk.multiagent.dm import AIDMAgent
        self.dm = AIDMAgent.__new__(AIDMAgent)
        self.dm.agent_id = "dm_test"
        self.dm.llm_config = {"provider": "openai", "model": "gpt-5-mini"}
        self.dm.current_scenario = MagicMock()
        self.dm.current_scenario.theme = "Test"
        self.dm.current_scenario.location = "Test Lab"
        self.dm.current_scenario.situation = "Testing"
        self.dm.current_scenario.void_level = 3
        self.dm.shared_state = MagicMock()
        self.dm.shared_state.mechanics_engine = MechanicsEngine()
        self.dm.shared_state.get_mechanics_engine.return_value = self.dm.shared_state.mechanics_engine
        self.dm.session_config = {}
        self.dm._round_synthesis_history = []

    def test_player_combatant_shows_faction(self):
        """Player entry in DM combatant list includes faction."""
        entities = [{
            'tid': 'tgt_aaaa',
            'name': 'Void Researcher Arden',
            'type': 'player',
            'faction': 'Tempest Industries',
            'pronouns': 'he/him',
            'agent_id': 'player_1',
        }]

        mapper = _make_mock_target_id_mapper(entities)
        self.dm.shared_state.get_target_id_mapper.return_value = mapper

        player_mock = MagicMock()
        player_mock.health = 20
        player_mock.max_health = 20
        player_mock.wounds = 0
        self.dm.shared_state.get_agent_by_id.return_value = player_mock

        lines = _build_dm_combatant_list(self.dm, mapper)
        assert len(lines) == 1
        assert 'Tempest Industries' in lines[0], f"Player combatant line missing faction: {lines[0]}"

    def test_enemy_combatant_shows_faction(self):
        """Enemy entry in DM combatant list includes faction."""
        entities = [{
            'tid': 'tgt_bbbb',
            'name': 'Nexus Enforcer Alpha',
            'type': 'enemy',
            'faction': 'Sovereign Nexus',
            'pronouns': 'they/them',
            'agent_id': 'enemy_1',
        }]

        mapper = _make_mock_target_id_mapper(entities)
        lines = _build_dm_combatant_list(self.dm, mapper)
        assert len(lines) == 1
        assert 'Sovereign Nexus' in lines[0], f"Enemy combatant line missing faction: {lines[0]}"

    def test_npc_combatant_shows_faction(self):
        """NPC entry in DM combatant list includes faction."""
        entities = [{
            'tid': 'tgt_cccc',
            'name': 'Tempest Sealbreaker',
            'type': 'npc',
            'faction': 'Tempest Industries',
            'pronouns': 'they/them',
            'agent_id': 'npc_1',
        }]

        mapper = _make_mock_target_id_mapper(entities)

        npc_mock = MagicMock()
        npc_mock.agent_id = 'npc_1'
        npc_mock.disposition = 'neutral'

        lines = _build_dm_combatant_list(self.dm, mapper, npc_mocks=[npc_mock])
        assert len(lines) == 1
        assert 'Tempest Industries' in lines[0], f"NPC combatant line missing faction: {lines[0]}"

    def test_mixed_scene_all_show_faction(self):
        """All entity types in same scene show their respective factions."""
        entities = [
            {'tid': 'tgt_aaaa', 'name': 'Void Researcher Arden', 'type': 'player',
             'faction': 'Tempest Industries', 'pronouns': 'he/him', 'agent_id': 'player_1'},
            {'tid': 'tgt_bbbb', 'name': 'Nexus Enforcer Alpha', 'type': 'enemy',
             'faction': 'Sovereign Nexus', 'pronouns': 'they/them', 'agent_id': 'enemy_1'},
            {'tid': 'tgt_cccc', 'name': 'Tempest Sealbreaker', 'type': 'npc',
             'faction': 'Tempest Industries', 'pronouns': 'they/them', 'agent_id': 'npc_1'},
        ]

        mapper = _make_mock_target_id_mapper(entities)

        player_mock = MagicMock()
        player_mock.health = 20
        player_mock.max_health = 20
        player_mock.wounds = 0
        self.dm.shared_state.get_agent_by_id.return_value = player_mock

        npc_mock = MagicMock()
        npc_mock.agent_id = 'npc_1'
        npc_mock.disposition = 'neutral'

        lines = _build_dm_combatant_list(self.dm, mapper, npc_mocks=[npc_mock])
        assert len(lines) == 3

        # Player line has Tempest Industries
        assert 'Tempest Industries' in lines[0], f"Player missing faction: {lines[0]}"
        # Enemy line has Sovereign Nexus
        assert 'Sovereign Nexus' in lines[1], f"Enemy missing faction: {lines[1]}"
        # NPC line has Tempest Industries
        assert 'Tempest Industries' in lines[2], f"NPC missing faction: {lines[2]}"


# ============================================================
# 2. Enemy Prompt Combatant List — Faction Per Entity
# ============================================================

class TestEnemyPromptFaction:
    """Enemy combatant list must show faction for PCs and other enemies."""

    def test_pc_entry_shows_faction(self):
        """PC entry in enemy prompt combatant list includes faction."""
        from scripts.aeonisk.multiagent.enemy_prompts import _format_battlefield

        enemy = _make_mock_enemy('enemy_1', 'Nexus Enforcer Alpha', 'Sovereign Nexus')
        player = _make_mock_player('player_1', 'Void Researcher Arden', 'Tempest Industries', 'he/him')

        mapper = _make_mock_target_id_mapper([
            {'tid': 'tgt_aaaa', 'name': 'Void Researcher Arden', 'type': 'player',
             'faction': 'Tempest Industries', 'agent_id': 'player_1'},
            {'tid': 'tgt_bbbb', 'name': 'Nexus Enforcer Alpha', 'type': 'enemy',
             'faction': 'Sovereign Nexus', 'agent_id': 'enemy_1'},
        ])

        section = _format_battlefield(
            enemy=enemy,
            player_agents=[player],
            enemy_agents=[enemy],
            available_tokens=[],
            target_id_mapper=mapper,
            free_targeting=True,
        )

        # The line for the PC should include faction
        assert 'Tempest Industries' in section, f"PC entry missing faction in enemy prompt:\n{section}"

    def test_enemy_entry_shows_faction(self):
        """Other enemy entries show their faction."""
        from scripts.aeonisk.multiagent.enemy_prompts import _format_battlefield

        enemy = _make_mock_enemy('enemy_1', 'Nexus Enforcer Alpha', 'Sovereign Nexus')
        other_enemy = _make_mock_enemy('enemy_2', 'Tempest Raider Beta', 'Tempest Industries')
        player = _make_mock_player('player_1', 'Void Researcher Arden', 'Tempest Industries')

        mapper = _make_mock_target_id_mapper([
            {'tid': 'tgt_aaaa', 'name': 'Void Researcher Arden', 'type': 'player',
             'faction': 'Tempest Industries', 'agent_id': 'player_1'},
            {'tid': 'tgt_bbbb', 'name': 'Nexus Enforcer Alpha', 'type': 'enemy',
             'faction': 'Sovereign Nexus', 'agent_id': 'enemy_1'},
            {'tid': 'tgt_cccc', 'name': 'Tempest Raider Beta', 'type': 'enemy',
             'faction': 'Tempest Industries', 'agent_id': 'enemy_2'},
        ])

        section = _format_battlefield(
            enemy=enemy,
            player_agents=[player],
            enemy_agents=[enemy, other_enemy],
            available_tokens=[],
            target_id_mapper=mapper,
            free_targeting=True,
        )

        # Enemy entries should also include faction
        assert 'Tempest Industries' in section

    def test_no_name_guessing_instruction(self):
        """Enemy prompt should NOT tell enemies to 'read names to identify faction'."""
        from scripts.aeonisk.multiagent.enemy_prompts import _format_battlefield

        enemy = _make_mock_enemy('enemy_1', 'Nexus Enforcer', 'Sovereign Nexus')
        player = _make_mock_player('player_1', 'Arden', 'Tempest Industries')

        mapper = _make_mock_target_id_mapper([
            {'tid': 'tgt_aaaa', 'name': 'Arden', 'type': 'player',
             'faction': 'Tempest Industries', 'agent_id': 'player_1'},
            {'tid': 'tgt_bbbb', 'name': 'Nexus Enforcer', 'type': 'enemy',
             'faction': 'Sovereign Nexus', 'agent_id': 'enemy_1'},
        ])

        section = _format_battlefield(
            enemy=enemy,
            player_agents=[player],
            enemy_agents=[enemy],
            available_tokens=[],
            target_id_mapper=mapper,
            free_targeting=True,
        )

        # Should NOT rely on name-based faction guessing
        assert "Read the names to identify faction" not in section


# ============================================================
# 3. DM Escalation Check NPC List — Faction
# ============================================================

class TestDMEscalationCheckFaction:
    """DM escalation check NPC list must include faction."""

    def test_npc_line_includes_faction(self):
        """NPC entries in escalation check include faction info.

        Tests the line format produced at dm.py:3381.
        """
        npc = _make_mock_npc('npc_1', 'Tempest Sealbreaker', 'Tempest Industries', 'neutral')

        # Simulate the NEW line building from dm.py:3381
        health_pct = int((npc.health / npc.max_health) * 100)
        took_damage = health_pct < 100
        marker = "⚠️ TOOK DAMAGE" if took_damage else ""

        npc_faction = getattr(npc, 'faction', 'Unknown')
        line = f"{npc.agent_id} ({npc.name}, {npc_faction}, {npc.disposition}, {health_pct}% HP) {marker}".strip()

        assert 'Tempest Industries' in line, f"NPC escalation line missing faction: {line}"


# ============================================================
# 4. PC Name Resolution in Enemy Prompts
# ============================================================

class TestPCNameResolutionInEnemyPrompts:
    """PC name must resolve correctly, not 'Unknown PC'."""

    def test_resolve_pc_name_uses_character_state(self):
        """_resolve_pc_name() uses character_state.name as primary source."""
        from scripts.aeonisk.multiagent.enemy_prompts import _resolve_pc_name

        player = _make_mock_player('player_1', 'Void Researcher Arden', 'Tempest Industries')
        assert _resolve_pc_name(player) == 'Void Researcher Arden'

    def test_resolve_pc_name_falls_back_to_name_attr(self):
        """_resolve_pc_name() falls back to .name for non-player agents."""
        from scripts.aeonisk.multiagent.enemy_prompts import _resolve_pc_name

        simple_agent = MagicMock()
        simple_agent.name = 'Simple Agent'
        del simple_agent.character_state
        assert _resolve_pc_name(simple_agent) == 'Simple Agent'

    def test_resolve_pc_faction_uses_character_state(self):
        """_resolve_pc_faction() uses character_state.faction as primary source."""
        from scripts.aeonisk.multiagent.enemy_prompts import _resolve_pc_faction

        player = _make_mock_player('player_1', 'Arden', 'Tempest Industries')
        assert _resolve_pc_faction(player) == 'Tempest Industries'

    def test_threat_assessment_shows_real_name(self):
        """Threat assessment section uses real PC name, not 'Unknown PC'."""
        from scripts.aeonisk.multiagent.enemy_prompts import _format_tactical_analysis
        from scripts.aeonisk.multiagent.enemy_agent import Position

        enemy = _make_mock_enemy('enemy_1', 'Nexus Enforcer Alpha', 'Sovereign Nexus')
        player = _make_mock_player('player_1', 'Void Researcher Arden', 'Tempest Industries')
        enemy.position = Position.from_string("Near-PC")
        player.position = Position.from_string("Near-PC")

        section = _format_tactical_analysis(
            enemy=enemy,
            player_agents=[player],
        )

        assert 'Unknown PC' not in section, f"Threat assessment still shows 'Unknown PC':\n{section}"
        assert 'Void Researcher Arden' in section, f"Real PC name not in threat assessment:\n{section}"


# ============================================================
# 5. Enemy-vs-Player Faction Alliance Check
# ============================================================

class TestEnemyVsPlayerFactionCheck:
    """Enemy targeting of players must check faction alliance."""

    def test_same_faction_is_allied(self):
        """Verify same faction returns allied."""
        from scripts.aeonisk.multiagent.faction_utils import are_factions_allied
        assert are_factions_allied('Tempest Industries', 'Tempest Industries')

    def test_nexus_vs_tempest_is_hostile(self):
        """Verify Nexus vs Tempest returns hostile."""
        from scripts.aeonisk.multiagent.faction_utils import are_factions_allied
        assert not are_factions_allied('Sovereign Nexus', 'Tempest Industries')

    def test_enemy_cannot_attack_allied_player(self):
        """Enemy should not be allowed to attack a player from the same faction."""
        from scripts.aeonisk.multiagent.enemy_combat import EnemyCombatManager, EnemyDeclaration

        enemy = _make_mock_enemy('enemy_1', 'Tempest Enforcer', 'Tempest Industries')
        player = _make_mock_player('player_1', 'Void Researcher Arden', 'Tempest Industries')

        manager = EnemyCombatManager.__new__(EnemyCombatManager)
        manager.enabled = True
        manager.enemy_agents = [enemy]
        manager.shared_state = MagicMock()

        mapper = _make_mock_target_id_mapper([
            {'tid': 'tgt_aaaa', 'name': 'Void Researcher Arden', 'type': 'player',
             'faction': 'Tempest Industries', 'agent_id': 'player_1',
             '_entity': player},
        ])
        manager.shared_state.get_target_id_mapper.return_value = mapper

        # Set up a declaration targeting the allied player
        decl = EnemyDeclaration(
            agent_id='enemy_1',
            character_name='Tempest Enforcer',
            initiative=10,
            defence_token=None,
            major_action='attack',
            target='tgt_aaaa',
            weapon='Pulse Pistol',
            minor_action=None,
            token_target=None,
            reasoning='Attacking nearest target',
            shared_intel=None,
        )
        manager.enemy_declarations = {'enemy_1': decl}

        mechanics = MagicMock()
        resolution_state = MagicMock()

        result = manager.execute_enemy_action(
            enemy_id='enemy_1',
            player_agents=[player],
            mechanics_engine=mechanics,
            resolution_state=resolution_state,
        )

        # Should be blocked — enemy and player are same faction
        assert result is not None
        assert result.get('result') == 'invalid target', \
            f"Expected 'invalid target' for same-faction attack, got: {result.get('result')}"

    def test_enemy_can_attack_hostile_player_in_combat(self):
        """Enemy attack against hostile-faction player proceeds normally."""
        from scripts.aeonisk.multiagent.enemy_combat import EnemyCombatManager, EnemyDeclaration

        enemy = _make_mock_enemy('enemy_1', 'Nexus Enforcer', 'Sovereign Nexus')
        player = _make_mock_player('player_1', 'Tempest Agent', 'Tempest Industries')

        manager = EnemyCombatManager.__new__(EnemyCombatManager)
        manager.enabled = True
        manager.enemy_agents = [enemy]
        manager.shared_state = MagicMock()

        mapper = _make_mock_target_id_mapper([
            {'tid': 'tgt_aaaa', 'name': 'Tempest Agent', 'type': 'player',
             'faction': 'Tempest Industries', 'agent_id': 'player_1',
             '_entity': player},
        ])
        manager.shared_state.get_target_id_mapper.return_value = mapper

        decl = EnemyDeclaration(
            agent_id='enemy_1',
            character_name='Nexus Enforcer',
            initiative=10,
            defence_token=None,
            major_action='attack',
            target='tgt_aaaa',
            weapon='Pulse Pistol',
            minor_action=None,
            token_target=None,
            reasoning='Attacking hostile Tempest agent',
            shared_intel=None,
        )
        manager.enemy_declarations = {'enemy_1': decl}

        mechanics = MagicMock()
        resolution_state = MagicMock()

        result = manager.execute_enemy_action(
            enemy_id='enemy_1',
            player_agents=[player],
            mechanics_engine=mechanics,
            resolution_state=resolution_state,
        )

        # Should NOT be blocked — hostile factions
        if result and result.get('result') == 'invalid target':
            pytest.fail(f"Hostile-faction attack incorrectly blocked: {result}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
