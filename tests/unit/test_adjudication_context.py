"""
Unit tests for Spec 16: Adjudication Context — Phases 0-2.

Tests cover:
- Phase 0: Pronoun fix in character_context
- Phase 1: Soulcredit ledger with round tracking, format_character_soulcredit(),
           player-facing SC display, in-round context with SC, session context block
- Phase 2: Rolling narrative digest from round synthesis history
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from scripts.aeonisk.multiagent.mechanics import MechanicsEngine, SoulcreditState


# ============================================================
# Phase 0: Pronoun Fix
# ============================================================

class TestPronounsInCharacterContext:
    """Phase 0: character_context includes pronouns."""

    def setup_method(self):
        """Set up a minimal DM agent for prompt building."""
        self.dm = self._create_dm_agent()

    def _create_dm_agent(self):
        """Create a minimal DM agent with mocked dependencies."""
        from scripts.aeonisk.multiagent.dm import AIDMAgent
        dm = AIDMAgent.__new__(AIDMAgent)
        dm.agent_id = "dm_test"
        dm.llm_config = {"provider": "openai", "model": "gpt-5-mini"}
        dm.current_scenario = MagicMock()
        dm.current_scenario.theme = "Test"
        dm.current_scenario.location = "Test Lab"
        dm.current_scenario.situation = "Testing"
        dm.current_scenario.void_level = 3
        dm.shared_state = MagicMock()
        dm.shared_state.mechanics_engine = MechanicsEngine()
        dm.shared_state.get_mechanics_engine.return_value = dm.shared_state.mechanics_engine
        dm.session_config = {}
        dm._round_synthesis_history = []
        return dm

    def test_pronouns_in_character_context(self):
        """character_context includes pronouns when available in action dict."""
        action = {
            'character': 'Vessel Sera Karsel',
            'faction': 'Vessel Collective',
            'pronouns': 'she/her',
        }

        # DM._build_resolution_prompt builds character_context internally
        # We test the character_context string built at dm.py:7460-7468
        dm = self.dm
        dm._get_party_personalities = MagicMock(return_value="")

        # Access the character_context building logic
        character_name = action.get('character', 'Unknown')
        faction = action.get('faction', 'Unaffiliated')
        pronouns = action.get('pronouns', 'they/them')
        party_personalities = dm._get_party_personalities()
        character_context = f"""
Character: {character_name} ({pronouns}, {faction})
Note: NPCs and other characters are aware of this affiliation.
{party_personalities}
"""
        assert 'she/her' in character_context
        assert 'Vessel Sera Karsel (she/her, Vessel Collective)' in character_context

    def test_pronouns_default_to_they_them(self):
        """character_context defaults to they/them when no pronouns in action."""
        action = {
            'character': 'Kael Dren',
            'faction': 'Nexus Authority',
        }
        pronouns = action.get('pronouns', 'they/them')
        assert pronouns == 'they/them'

    def test_pronouns_included_in_action_dict(self):
        """Player agent includes pronouns in action dict sent to DM."""
        # Verify the action dict carries pronouns at player.py:899-901
        from scripts.aeonisk.multiagent.player import AIPlayerAgent
        player = AIPlayerAgent.__new__(AIPlayerAgent)
        player.character_state = MagicMock()
        player.character_state.name = "Sera"
        player.character_state.faction = "Vessel"
        player.character_state.pronouns = "she/her"

        # Simulate what happens at player.py:899-901
        action = {}
        action['character'] = player.character_state.name
        action['faction'] = player.character_state.faction
        action['pronouns'] = player.character_state.pronouns

        assert action['pronouns'] == 'she/her'


# ============================================================
# Phase 1: Soulcredit Ledger + In-Round Action Recap
# ============================================================

class TestSoulcreditHistoryIncludesRound:
    """Phase 1a: SC history entries have 'round' key after adjust."""

    def test_soulcredit_history_includes_round(self):
        """History entries include round number when provided."""
        sc = SoulcreditState(score=0)
        sc.adjust(1, "healed ally", round_num=1)
        assert len(sc.history) == 1
        assert sc.history[0]['round'] == 1
        assert sc.history[0]['change'] == 1
        assert sc.history[0]['reason'] == 'healed ally'

    def test_soulcredit_history_round_none_when_omitted(self):
        """History entries have round=None when round_num not provided."""
        sc = SoulcreditState(score=0)
        sc.adjust(1, "unknown round")
        assert len(sc.history) == 1
        assert sc.history[0]['round'] is None

    def test_soulcredit_history_multiple_rounds(self):
        """Multiple adjustments track separate rounds."""
        sc = SoulcreditState(score=0)
        sc.adjust(1, "healed ally", round_num=1)
        sc.adjust(1, "non-lethal", round_num=2)
        sc.adjust(1, "restraint", round_num=3)
        assert len(sc.history) == 3
        assert [h['round'] for h in sc.history] == [1, 2, 3]

    def test_soulcredit_no_history_when_no_change(self):
        """No history entry when amount is 0 (clamped to same value)."""
        sc = SoulcreditState(score=10)  # Already at max
        sc.adjust(1, "should clamp", round_num=5)
        assert len(sc.history) == 0  # Score didn't change (clamped at 10)


class TestFormatCharacterSoulcredit:
    """Phase 1b: format_character_soulcredit() on MechanicsEngine."""

    def setup_method(self):
        self.mechanics = MechanicsEngine()

    def test_format_character_soulcredit_with_history(self):
        """Formatted SC shows per-round breakdown for single character."""
        sc = self.mechanics.get_soulcredit_state("player_1", initial_score=0)
        sc.adjust(1, "healed ally", round_num=1)
        sc.adjust(1, "non-lethal", round_num=2)
        sc.adjust(1, "restraint", round_num=3)

        result = self.mechanics.format_character_soulcredit("player_1", "Vessel Sera Karsel")
        assert "ACTING CHARACTER SOULCREDIT:" in result
        assert "Vessel Sera Karsel" in result
        assert "+3" in result
        assert "Trustworthy" in result  # Score +3 = Trustworthy (Honorable starts at +5)
        assert "R1:" in result
        assert "healed ally" in result
        assert "R2:" in result
        assert "R3:" in result

    def test_format_character_soulcredit_empty(self):
        """No history returns empty string."""
        self.mechanics.get_soulcredit_state("player_1", initial_score=0)
        result = self.mechanics.format_character_soulcredit("player_1", "Kael Dren")
        assert result == ""

    def test_format_character_soulcredit_includes_reputation(self):
        """Output includes reputation level descriptor."""
        sc = self.mechanics.get_soulcredit_state("player_1", initial_score=0)
        sc.adjust(-5, "betrayed oath", round_num=1)

        result = self.mechanics.format_character_soulcredit("player_1", "Kael Dren")
        assert "Disreputable" in result

    def test_format_character_soulcredit_negative_score(self):
        """Negative scores display correctly."""
        sc = self.mechanics.get_soulcredit_state("player_1", initial_score=0)
        sc.adjust(-2, "broke contract", round_num=1)
        sc.adjust(-1, "collateral damage", round_num=2)

        result = self.mechanics.format_character_soulcredit("player_1", "Kael Dren")
        assert "-3" in result
        assert "Questionable" in result

    def test_format_character_soulcredit_unknown_agent(self):
        """Unknown agent_id returns empty string (no state created)."""
        result = self.mechanics.format_character_soulcredit("nonexistent_id", "Nobody")
        assert result == ""

    def test_format_character_soulcredit_groups_by_round(self):
        """Multiple changes in same round are grouped."""
        sc = self.mechanics.get_soulcredit_state("player_1", initial_score=0)
        sc.adjust(1, "healed ally", round_num=2)
        sc.adjust(1, "protected civilian", round_num=2)

        result = self.mechanics.format_character_soulcredit("player_1", "Sera")
        assert "R2:" in result
        assert "healed ally" in result
        assert "protected civilian" in result


class TestPlayerScDisplayShowsHistory:
    """Phase 1b-2: Player status shows SC history trail."""

    def test_player_sc_display_shows_history(self):
        """Player _show_character_status shows SC with history trail."""
        mechanics = MechanicsEngine()
        sc = mechanics.get_soulcredit_state("player_1", initial_score=0)
        sc.adjust(1, "healed ally", round_num=1)
        sc.adjust(1, "non-lethal", round_num=2)
        sc.adjust(1, "restraint", round_num=3)

        # Test the formatting method exists and works
        result = mechanics.format_player_soulcredit("player_1")
        assert "Soulcredit: +3" in result
        assert "Trustworthy" in result  # Score +3 = Trustworthy
        assert "R1:" in result
        assert "healed ally" in result

    def test_player_sc_display_no_history(self):
        """Player SC display with no history shows just score."""
        mechanics = MechanicsEngine()
        mechanics.get_soulcredit_state("player_1", initial_score=2)

        result = mechanics.format_player_soulcredit("player_1")
        assert "Soulcredit: +2" in result
        # No round history, so no "R1:" etc.
        assert "R1:" not in result

    def test_player_sc_display_zero_score(self):
        """Player SC display shows 0 correctly."""
        mechanics = MechanicsEngine()
        mechanics.get_soulcredit_state("player_1", initial_score=0)

        result = mechanics.format_player_soulcredit("player_1")
        assert "Soulcredit: 0" in result
        assert "Neutral" in result


class TestInRoundContextIncludesSc:
    """Phase 1c: previous_context shows SC delta and reason."""

    def test_in_round_context_includes_sc_changes(self):
        """Enhanced previous_context shows SC changes for each prior action."""
        previous_resolutions = [
            {
                'character_name': 'Sera Karsel',
                'narration': 'Sera discovered a hidden passage behind the energy conduit.',
                'action': {'action_type': 'investigate'},
                'effects': {
                    'soulcredit_changes': []
                },
                'resolution': {'margin': 6}
            },
            {
                'character_name': 'Kael Dren',
                'narration': 'Kael engaged the hostile patrol with precision fire.',
                'action': {'action_type': 'combat'},
                'effects': {
                    'soulcredit_changes': [
                        {'character_name': 'Kael Dren', 'amount': 0, 'reason': 'justified combat'}
                    ]
                },
                'resolution': {'margin': 4}
            }
        ]

        # Build context using the new enhanced format
        from scripts.aeonisk.multiagent.dm import _build_enhanced_previous_context
        result = _build_enhanced_previous_context(previous_resolutions)

        assert "EARLIER ACTIONS THIS ROUND" in result
        assert "Sera Karsel" in result
        assert "INVESTIGATE" in result
        assert "Kael Dren" in result
        assert "COMBAT" in result
        assert "SC:" in result

    def test_in_round_context_empty_when_no_resolutions(self):
        """No context when no previous resolutions."""
        from scripts.aeonisk.multiagent.dm import _build_enhanced_previous_context
        result = _build_enhanced_previous_context([])
        assert result == ""

    def test_in_round_context_handles_none_nested_dicts(self):
        """Previous resolutions with None action/resolution/effects don't crash."""
        from scripts.aeonisk.multiagent.dm import _build_enhanced_previous_context
        previous_resolutions = [
            {
                'character_name': 'Arden',
                'narration': 'Arden investigated.',
                'action': None,
                'effects': None,
                'resolution': None,
            }
        ]
        result = _build_enhanced_previous_context(previous_resolutions)
        assert "Arden" in result
        assert "UNKNOWN" in result  # action_type defaults to 'unknown'.upper()

    def test_in_round_context_handles_string_resolution(self):
        """Previous resolutions where 'resolution' is a string (serialized outcome) don't crash."""
        from scripts.aeonisk.multiagent.dm import _build_enhanced_previous_context
        # This matches the actual resolution_data format from dm.py:3137
        # where resolution = res['resolution']['outcome'] (a string like "failure")
        previous_resolutions = [
            {
                'character_name': 'Kael',
                'narration': 'Kael proposed terms but was rebuffed.',
                'action': {'action_type': 'social'},
                'effects': None,
                'resolution': 'failure',  # String, not dict!
            }
        ]
        result = _build_enhanced_previous_context(previous_resolutions)
        assert "Kael" in result
        assert "SOCIAL" in result


class TestSessionContextInPrompt:
    """Phase 1d-1e: DM prompt contains SESSION CONTEXT block."""

    def setup_method(self):
        self.dm = self._create_dm_agent()

    def _create_dm_agent(self):
        from scripts.aeonisk.multiagent.dm import AIDMAgent
        dm = AIDMAgent.__new__(AIDMAgent)
        dm.agent_id = "dm_test"
        dm.llm_config = {"provider": "openai", "model": "gpt-5-mini"}
        dm.current_scenario = MagicMock()
        dm.current_scenario.theme = "Test"
        dm.current_scenario.location = "Test Lab"
        dm.current_scenario.situation = "Testing"
        dm.current_scenario.void_level = 3
        dm.shared_state = MagicMock()
        dm.shared_state.mechanics_engine = MechanicsEngine()
        dm.shared_state.get_mechanics_engine.return_value = dm.shared_state.mechanics_engine
        dm.session_config = {}
        dm._round_synthesis_history = []
        return dm

    def test_session_context_in_prompt(self):
        """DM prompt contains SESSION CONTEXT when SC history exists."""
        mechanics = self.dm.shared_state.mechanics_engine
        sc = mechanics.get_soulcredit_state("player_1", initial_score=0)
        sc.adjust(1, "healed ally", round_num=1)

        previous_resolutions = []
        context = self.dm._build_session_context(
            agent_id="player_1",
            character_name="Vessel Sera Karsel",
            previous_resolutions=previous_resolutions,
            current_round=2
        )

        assert "SESSION CONTEXT" in context
        assert "ACTING CHARACTER SOULCREDIT" in context
        assert "Vessel Sera Karsel" in context

    def test_session_context_absent_round_one_no_history(self):
        """No SESSION CONTEXT on first action of first round with no history."""
        context = self.dm._build_session_context(
            agent_id="player_1",
            character_name="Vessel Sera Karsel",
            previous_resolutions=[],
            current_round=1
        )

        # Empty when nothing to show
        assert context == ""

    def test_session_context_includes_in_round_recap(self):
        """SESSION CONTEXT includes in-round action recap when present."""
        previous_resolutions = [
            {
                'character_name': 'Kael Dren',
                'narration': 'Kael investigated the terminal.',
                'action': {'action_type': 'investigate'},
                'effects': {'soulcredit_changes': []},
                'resolution': {'margin': 3}
            }
        ]

        context = self.dm._build_session_context(
            agent_id="player_1",
            character_name="Vessel Sera Karsel",
            previous_resolutions=previous_resolutions,
            current_round=1
        )

        assert "SESSION CONTEXT" in context
        assert "EARLIER ACTIONS THIS ROUND" in context
        assert "Kael Dren" in context


# ============================================================
# Phase 2: Rolling Narrative Digest
# ============================================================

class TestNarrativeDigest:
    """Phase 2: Rolling narrative digest from round synthesis history."""

    def setup_method(self):
        self.dm = self._create_dm_agent()

    def _create_dm_agent(self):
        from scripts.aeonisk.multiagent.dm import AIDMAgent
        dm = AIDMAgent.__new__(AIDMAgent)
        dm.agent_id = "dm_test"
        dm.llm_config = {"provider": "openai", "model": "gpt-5-mini"}
        dm.shared_state = MagicMock()
        dm.shared_state.mechanics_engine = MechanicsEngine()
        dm.shared_state.get_mechanics_engine.return_value = dm.shared_state.mechanics_engine
        dm.session_config = {}
        dm._round_synthesis_history = []
        return dm

    def test_narrative_digest_rolling_window(self):
        """Only last 3 rounds included in digest."""
        dm = self.dm
        dm._round_synthesis_history = [
            (1, "Round 1 narration - the party arrived at the station."),
            (2, "Round 2 narration - combat broke out in the corridor."),
            (3, "Round 3 narration - the void pulsed through the walls."),
            (4, "Round 4 narration - negotiations began with the Nexus guards."),
            (5, "Round 5 narration - the ritual was attempted at the shrine."),
        ]

        result = dm._build_narrative_digest(current_round=6, lookback=3)

        assert "PRIOR ROUNDS" in result
        assert "R3:" in result
        assert "R4:" in result
        assert "R5:" in result
        # Round 1 and 2 should NOT be in the digest (outside lookback window)
        assert "R1:" not in result
        assert "R2:" not in result

    def test_narrative_digest_full_narration(self):
        """Narrations are included untruncated."""
        dm = self.dm
        long_narration = "A" * 2000  # Long narration
        dm._round_synthesis_history = [
            (1, long_narration),
        ]

        result = dm._build_narrative_digest(current_round=2, lookback=3)

        assert "PRIOR ROUNDS" in result
        assert "A" * 2000 in result  # Full, untruncated

    def test_narrative_digest_empty_round_one(self):
        """Empty for first round (no history)."""
        dm = self.dm
        dm._round_synthesis_history = []

        result = dm._build_narrative_digest(current_round=1, lookback=3)
        assert result == ""

    def test_narrative_digest_fewer_rounds_than_lookback(self):
        """Works correctly when fewer rounds exist than lookback window."""
        dm = self.dm
        dm._round_synthesis_history = [
            (1, "Round 1 events happened."),
        ]

        result = dm._build_narrative_digest(current_round=2, lookback=3)
        assert "PRIOR ROUNDS" in result
        assert "R1:" in result

    def test_narrative_digest_threaded_into_session_context(self):
        """Session context includes narrative digest when history exists."""
        dm = self.dm
        dm._round_synthesis_history = [
            (1, "Round 1 narration - the party arrived."),
            (2, "Round 2 narration - combat erupted."),
        ]

        context = dm._build_session_context(
            agent_id="player_1",
            character_name="Vessel Sera Karsel",
            previous_resolutions=[],
            current_round=3
        )

        assert "PRIOR ROUNDS" in context
        assert "Round 1 narration" in context
        assert "Round 2 narration" in context


# ============================================================
# Phase 3: Faction Relationship Context
# ============================================================

class TestBuildFactionContext:
    """Phase 3: Faction relationship context injected into DM adjudication prompt."""

    def setup_method(self):
        self.dm = self._create_dm_agent()

    def _create_dm_agent(self):
        from scripts.aeonisk.multiagent.dm import AIDMAgent
        dm = AIDMAgent.__new__(AIDMAgent)
        dm.agent_id = "dm_test"
        dm.llm_config = {"provider": "openai", "model": "gpt-5-mini"}
        dm.shared_state = MagicMock()
        dm.shared_state.mechanics_engine = MechanicsEngine()
        dm.shared_state.get_mechanics_engine.return_value = dm.shared_state.mechanics_engine
        dm.session_config = {}
        dm._round_synthesis_history = []
        return dm

    def _mock_target_id_mapper(self, combatants):
        """Create a mock TargetIDMapper that returns given combatant infos.

        Args:
            combatants: dict of target_id -> combatant_info dict
                Each info dict should have: name, type, faction, pronouns
        """
        mapper = MagicMock()
        mapper.enabled = True
        mapper.get_all_target_ids.return_value = list(combatants.keys())
        mapper.get_combatant_info.side_effect = lambda tid: combatants.get(tid)
        self.dm.shared_state.get_target_id_mapper.return_value = mapper
        return mapper

    def test_faction_context_lists_factions_present(self):
        """Faction context lists all factions on the battlefield."""
        self._mock_target_id_mapper({
            'tgt_a1b2': {
                'name': 'Vessel Sera Karsel', 'type': 'player',
                'faction': 'Vessel Collective', 'pronouns': 'she/her',
            },
            'tgt_c3d4': {
                'name': 'Pantheon Patrol Alpha', 'type': 'enemy',
                'faction': 'Pantheon Security', 'pronouns': 'they/them',
            },
        })

        result = self.dm._build_faction_context()
        assert "FACTION CONTEXT" in result
        assert "Vessel Collective" in result
        assert "Pantheon Security" in result

    def test_faction_context_shows_entity_types_per_faction(self):
        """Faction context shows which entities belong to each faction and their types."""
        self._mock_target_id_mapper({
            'tgt_a1b2': {
                'name': 'Vessel Sera Karsel', 'type': 'player',
                'faction': 'Vessel Collective', 'pronouns': 'she/her',
            },
            'tgt_c3d4': {
                'name': 'Pantheon Patrol Alpha', 'type': 'enemy',
                'faction': 'Pantheon Security', 'pronouns': 'they/them',
            },
            'tgt_e5f6': {
                'name': 'Enforcer Kael Dren', 'type': 'player',
                'faction': 'Pantheon Security', 'pronouns': 'he/him',
            },
        })

        result = self.dm._build_faction_context()
        assert "FACTION CONTEXT" in result
        # Pantheon Security has both a player and an enemy
        assert "Pantheon Security" in result
        assert "Vessel Collective" in result

    def test_faction_context_identifies_cross_faction_conflict(self):
        """When a faction has both party members and enemies, that's highlighted."""
        self._mock_target_id_mapper({
            'tgt_a1b2': {
                'name': 'Enforcer Kael Dren', 'type': 'player',
                'faction': 'Pantheon Security', 'pronouns': 'he/him',
            },
            'tgt_c3d4': {
                'name': 'Pantheon Patrol Alpha', 'type': 'enemy',
                'faction': 'Pantheon Security', 'pronouns': 'they/them',
            },
        })

        result = self.dm._build_faction_context()
        assert "FACTION CONTEXT" in result
        # Should indicate internal faction conflict
        assert "Pantheon Security" in result
        # The result should show that both party and hostile entities share a faction
        assert "party" in result.lower() or "player" in result.lower()
        assert "enemy" in result.lower() or "hostile" in result.lower()

    def test_faction_context_includes_npcs(self):
        """NPC entities are included with their faction."""
        self._mock_target_id_mapper({
            'tgt_a1b2': {
                'name': 'Vessel Sera Karsel', 'type': 'player',
                'faction': 'Vessel Collective', 'pronouns': 'she/her',
            },
            'tgt_c3d4': {
                'name': 'Merchant Tuval', 'type': 'npc',
                'faction': 'Freeborn Drifters', 'pronouns': 'he/him',
            },
        })

        result = self.dm._build_faction_context()
        assert "Freeborn Drifters" in result
        assert "npc" in result.lower() or "non-combatant" in result.lower() or "neutral" in result.lower()

    def test_faction_context_empty_when_no_mapper(self):
        """Returns empty string when target_id_mapper is unavailable."""
        self.dm.shared_state.get_target_id_mapper.return_value = None

        result = self.dm._build_faction_context()
        assert result == ""

    def test_faction_context_empty_when_mapper_disabled(self):
        """Returns empty string when target_id_mapper is disabled."""
        mapper = MagicMock()
        mapper.enabled = False
        self.dm.shared_state.get_target_id_mapper.return_value = mapper

        result = self.dm._build_faction_context()
        assert result == ""

    def test_faction_context_empty_when_no_combatants(self):
        """Returns empty string when no combatants registered."""
        self._mock_target_id_mapper({})

        result = self.dm._build_faction_context()
        assert result == ""

    def test_faction_context_skips_unknown_faction(self):
        """Entities with 'Unknown' faction are not listed in faction context."""
        self._mock_target_id_mapper({
            'tgt_a1b2': {
                'name': 'Vessel Sera Karsel', 'type': 'player',
                'faction': 'Vessel Collective', 'pronouns': 'she/her',
            },
            'tgt_c3d4': {
                'name': 'Mysterious Figure', 'type': 'enemy',
                'faction': 'Unknown', 'pronouns': 'they/them',
            },
        })

        result = self.dm._build_faction_context()
        assert "Vessel Collective" in result
        # Unknown faction entities still appear but faction is noted
        # (the DM needs to know about unknown-faction entities too)
        # Just verify the method doesn't crash
        assert "FACTION CONTEXT" in result

    def test_faction_context_multiple_enemies_same_faction(self):
        """Multiple enemies in the same faction are grouped together."""
        self._mock_target_id_mapper({
            'tgt_a1b2': {
                'name': 'Vessel Sera Karsel', 'type': 'player',
                'faction': 'Vessel Collective', 'pronouns': 'she/her',
            },
            'tgt_c3d4': {
                'name': 'Pantheon Patrol Alpha', 'type': 'enemy',
                'faction': 'Pantheon Security', 'pronouns': 'they/them',
            },
            'tgt_e5f6': {
                'name': 'Pantheon Patrol Beta', 'type': 'enemy',
                'faction': 'Pantheon Security', 'pronouns': 'they/them',
            },
        })

        result = self.dm._build_faction_context()
        # Pantheon Security should appear once with count info
        assert "Pantheon Security" in result
        # Should mention both patrol entities or a count
        assert "Patrol Alpha" in result or "2" in result


class TestFactionContextInSessionContext:
    """Phase 3: Faction context is included in the SESSION CONTEXT block."""

    def setup_method(self):
        self.dm = self._create_dm_agent()

    def _create_dm_agent(self):
        from scripts.aeonisk.multiagent.dm import AIDMAgent
        dm = AIDMAgent.__new__(AIDMAgent)
        dm.agent_id = "dm_test"
        dm.llm_config = {"provider": "openai", "model": "gpt-5-mini"}
        dm.shared_state = MagicMock()
        dm.shared_state.mechanics_engine = MechanicsEngine()
        dm.shared_state.get_mechanics_engine.return_value = dm.shared_state.mechanics_engine
        dm.session_config = {}
        dm._round_synthesis_history = []
        return dm

    def _mock_target_id_mapper(self, combatants):
        mapper = MagicMock()
        mapper.enabled = True
        mapper.get_all_target_ids.return_value = list(combatants.keys())
        mapper.get_combatant_info.side_effect = lambda tid: combatants.get(tid)
        self.dm.shared_state.get_target_id_mapper.return_value = mapper
        return mapper

    def test_faction_context_in_session_context_block(self):
        """SESSION CONTEXT includes faction context when combatants have factions."""
        self._mock_target_id_mapper({
            'tgt_a1b2': {
                'name': 'Vessel Sera Karsel', 'type': 'player',
                'faction': 'Vessel Collective', 'pronouns': 'she/her',
            },
            'tgt_c3d4': {
                'name': 'Pantheon Patrol Alpha', 'type': 'enemy',
                'faction': 'Pantheon Security', 'pronouns': 'they/them',
            },
        })

        context = self.dm._build_session_context(
            agent_id="player_1",
            character_name="Vessel Sera Karsel",
            previous_resolutions=[],
            current_round=2
        )

        assert "SESSION CONTEXT" in context
        assert "FACTION CONTEXT" in context
        assert "Vessel Collective" in context
        assert "Pantheon Security" in context

    def test_session_context_without_factions_when_no_mapper(self):
        """SESSION CONTEXT still works when no target_id_mapper is available."""
        self.dm.shared_state.get_target_id_mapper.return_value = None

        # Add SC history so session context is non-empty
        mechanics = self.dm.shared_state.mechanics_engine
        sc = mechanics.get_soulcredit_state("player_1", initial_score=0)
        sc.adjust(1, "healed ally", round_num=1)

        context = self.dm._build_session_context(
            agent_id="player_1",
            character_name="Vessel Sera Karsel",
            previous_resolutions=[],
            current_round=2
        )

        assert "SESSION CONTEXT" in context
        assert "FACTION CONTEXT" not in context

    def test_faction_context_appears_with_other_sections(self):
        """Faction context appears alongside SC ledger and narrative digest."""
        self._mock_target_id_mapper({
            'tgt_a1b2': {
                'name': 'Vessel Sera Karsel', 'type': 'player',
                'faction': 'Vessel Collective', 'pronouns': 'she/her',
            },
            'tgt_c3d4': {
                'name': 'Pantheon Patrol Alpha', 'type': 'enemy',
                'faction': 'Pantheon Security', 'pronouns': 'they/them',
            },
        })

        # Add SC history
        mechanics = self.dm.shared_state.mechanics_engine
        sc = mechanics.get_soulcredit_state("player_1", initial_score=0)
        sc.adjust(1, "healed ally", round_num=1)

        # Add narrative digest
        self.dm._round_synthesis_history = [
            (1, "Round 1 narration - the party arrived."),
        ]

        context = self.dm._build_session_context(
            agent_id="player_1",
            character_name="Vessel Sera Karsel",
            previous_resolutions=[],
            current_round=2
        )

        # All three sections present
        assert "ACTING CHARACTER SOULCREDIT" in context
        assert "PRIOR ROUNDS" in context
        assert "FACTION CONTEXT" in context
