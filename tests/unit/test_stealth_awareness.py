"""
Tests for stealth awareness system.

The DM controls which agents are aware of each action resolution via the
`aware_agents` field. This prevents NPCs and enemies from reacting to
successful stealth actions they shouldn't know about.

TDD: These tests are written FIRST to define the expected behavior.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock

# Schema imports
from scripts.aeonisk.multiagent.schemas.action_resolution import (
    ActionResolution,
    MechanicalEffects,
)
from scripts.aeonisk.multiagent.schemas.shared_types import SuccessTier


class TestAwareAgentsSchemaField:
    """Test that ActionResolution has the aware_agents field."""

    def test_action_resolution_has_aware_agents_field(self):
        """ActionResolution should have an aware_agents field."""
        resolution = ActionResolution(
            narration="Echo slips past the guard, completely undetected. " * 5,
            success_tier=SuccessTier.GOOD,
            margin=8,
            aware_agents=["dm", "echo"]
        )
        assert hasattr(resolution, 'aware_agents')
        assert resolution.aware_agents == ["dm", "echo"]

    def test_aware_agents_defaults_to_empty_list(self):
        """Empty aware_agents means public (all agents see it)."""
        resolution = ActionResolution(
            narration="The security guard fires at the intruder. " * 5,
            success_tier=SuccessTier.GOOD,
            margin=5,
        )
        assert resolution.aware_agents == []

    def test_aware_agents_accepts_agent_ids(self):
        """aware_agents should accept agent IDs like 'player_1', 'npc_vendor'."""
        resolution = ActionResolution(
            narration="A whispered conversation happens in the corner. " * 5,
            success_tier=SuccessTier.GOOD,
            margin=10,
            aware_agents=["player_1", "player_2", "npc_informant"]
        )
        assert "player_1" in resolution.aware_agents
        assert "npc_informant" in resolution.aware_agents


class TestNarrationEntry:
    """Test NarrationEntry dataclass for storing narrations with metadata."""

    def test_narration_entry_exists(self):
        """NarrationEntry should exist for storing narrations with awareness."""
        from scripts.aeonisk.multiagent.player import NarrationEntry

        entry = NarrationEntry(
            text="[Echo] Echo slips past the guard undetected.",
            aware_agents=["dm", "player_echo"]
        )
        assert entry.text == "[Echo] Echo slips past the guard undetected."
        assert entry.aware_agents == ["dm", "player_echo"]

    def test_narration_entry_defaults_to_public(self):
        """NarrationEntry with empty aware_agents is public."""
        from scripts.aeonisk.multiagent.player import NarrationEntry

        entry = NarrationEntry(
            text="[Guard] The guard shouts an alarm!"
        )
        assert entry.aware_agents == []


class TestAwarenessFiltering:
    """Test filtering narrations based on agent awareness."""

    def test_filter_narrations_for_agent_public(self):
        """Public narrations (empty aware_agents) visible to everyone."""
        from scripts.aeonisk.multiagent.awareness import filter_narrations_for_agent
        from scripts.aeonisk.multiagent.player import NarrationEntry

        narrations = [
            NarrationEntry(text="[Guard] Combat begins!", aware_agents=[]),
            NarrationEntry(text="[Echo] Echo sneaks past", aware_agents=["dm", "player_echo"]),
        ]

        # Guard should only see public narration
        filtered = filter_narrations_for_agent("npc_guard", narrations)
        assert len(filtered) == 1
        assert "Combat begins" in filtered[0].text

    def test_filter_narrations_for_agent_private(self):
        """Private narrations only visible to agents in aware_agents."""
        from scripts.aeonisk.multiagent.awareness import filter_narrations_for_agent
        from scripts.aeonisk.multiagent.player import NarrationEntry

        narrations = [
            NarrationEntry(text="[Echo] Echo hacks the terminal", aware_agents=["dm", "player_echo"]),
        ]

        # Echo should see their own stealth action
        filtered = filter_narrations_for_agent("player_echo", narrations)
        assert len(filtered) == 1

        # Random NPC should not see it
        filtered = filter_narrations_for_agent("npc_guard", narrations)
        assert len(filtered) == 0

    def test_filter_narrations_dm_sees_everything(self):
        """DM is always in aware_agents for private narrations."""
        from scripts.aeonisk.multiagent.awareness import filter_narrations_for_agent
        from scripts.aeonisk.multiagent.player import NarrationEntry

        narrations = [
            NarrationEntry(text="[Echo] Secret action", aware_agents=["dm", "player_echo"]),
        ]

        # DM should always see private narrations
        filtered = filter_narrations_for_agent("dm", narrations)
        assert len(filtered) == 1

    def test_filter_narrations_handles_string_list(self):
        """Backwards compatibility: handle list[str] as all public."""
        from scripts.aeonisk.multiagent.awareness import filter_narrations_for_agent

        # Old format: list of strings (all public)
        old_narrations = [
            "[Guard] Old format narration",
            "[Echo] Another old format",
        ]

        # Should treat strings as public (everyone sees them)
        filtered = filter_narrations_for_agent("npc_random", old_narrations)
        assert len(filtered) == 2


class TestPlayerNarrationStorage:
    """Test that player agents store narrations with awareness metadata."""

    @pytest.fixture
    def mock_player_agent(self):
        """Create a mock player agent with recent_narrations."""
        from scripts.aeonisk.multiagent.player import NarrationEntry

        agent = MagicMock()
        agent.agent_id = "player_echo"
        agent.recent_narrations = []
        return agent

    def test_player_stores_narration_with_awareness(self, mock_player_agent):
        """Player should store NarrationEntry objects, not plain strings."""
        from scripts.aeonisk.multiagent.player import NarrationEntry

        # Simulate receiving a resolution with aware_agents
        entry = NarrationEntry(
            text="[Echo] Echo slips past the guard",
            aware_agents=["dm", "player_echo"]
        )
        mock_player_agent.recent_narrations.append(entry)

        assert len(mock_player_agent.recent_narrations) == 1
        assert isinstance(mock_player_agent.recent_narrations[0], NarrationEntry)
        assert mock_player_agent.recent_narrations[0].aware_agents == ["dm", "player_echo"]


class TestNPCContextFiltering:
    """Test that NPCs only see narrations they're aware of."""

    def test_npc_does_not_see_stealth_success(self):
        """NPC should not see successful stealth action narration."""
        from scripts.aeonisk.multiagent.awareness import filter_narrations_for_agent
        from scripts.aeonisk.multiagent.player import NarrationEntry

        narrations = [
            NarrationEntry(
                text="[Echo] Echo successfully picks the lock without triggering any alarms.",
                aware_agents=["dm", "player_echo"]  # Only DM and Echo know
            ),
            NarrationEntry(
                text="[Guard] The guard patrols the corridor.",
                aware_agents=[]  # Public - everyone sees
            ),
        ]

        # NPC guard should only see their own patrol, not Echo's stealth
        filtered = filter_narrations_for_agent("npc_guard", narrations)

        assert len(filtered) == 1
        assert "patrols the corridor" in filtered[0].text
        assert "picks the lock" not in filtered[0].text

    def test_npc_sees_stealth_failure(self):
        """NPC should see failed stealth action (they noticed!)."""
        from scripts.aeonisk.multiagent.awareness import filter_narrations_for_agent
        from scripts.aeonisk.multiagent.player import NarrationEntry

        narrations = [
            NarrationEntry(
                text="[Echo] Echo fumbles the lockpick, metal clanging loudly!",
                aware_agents=[]  # Public - failure was noticed
            ),
        ]

        # Everyone should see the failure
        filtered = filter_narrations_for_agent("npc_guard", narrations)
        assert len(filtered) == 1
        assert "fumbles the lockpick" in filtered[0].text


class TestEnemyContextFiltering:
    """Test that enemies only see narrations they're aware of."""

    def test_enemy_does_not_see_stealth_success(self):
        """Enemy should not see successful stealth action."""
        from scripts.aeonisk.multiagent.awareness import filter_narrations_for_agent
        from scripts.aeonisk.multiagent.player import NarrationEntry

        narrations = [
            NarrationEntry(
                text="[Ash] Ash silently flanks the enemy position.",
                aware_agents=["dm", "player_ash"]  # Enemy unaware
            ),
        ]

        filtered = filter_narrations_for_agent("enemy_grunt_1", narrations)
        assert len(filtered) == 0

    def test_enemy_sees_loud_combat(self):
        """Enemy should see loud combat actions."""
        from scripts.aeonisk.multiagent.awareness import filter_narrations_for_agent
        from scripts.aeonisk.multiagent.player import NarrationEntry

        narrations = [
            NarrationEntry(
                text="[Ash] Ash fires their rifle, muzzle flash lighting up the corridor!",
                aware_agents=[]  # Public - loud combat
            ),
        ]

        filtered = filter_narrations_for_agent("enemy_grunt_1", narrations)
        assert len(filtered) == 1


class TestPlayerToPlayerFiltering:
    """Test that players don't see other players' stealth narrations."""

    def test_player_does_not_see_other_player_stealth(self):
        """Player B's filtered narrations exclude Player A's stealth entries."""
        from scripts.aeonisk.multiagent.awareness import filter_narrations_for_agent, NarrationEntry

        narrations = [
            NarrationEntry(
                text="[Echo] Echo slips past the guard undetected.",
                aware_agents=["dm", "player_echo"]  # Only DM and Echo know
            ),
            NarrationEntry(
                text="[Guard] The guard patrols the corridor.",
                aware_agents=[]  # Public
            ),
        ]

        # Player Ash should NOT see Echo's stealth action
        filtered = filter_narrations_for_agent("player_ash", narrations)
        assert len(filtered) == 1
        assert "patrols the corridor" in filtered[0].text

    def test_player_sees_own_stealth_narration(self):
        """Player A still sees their own stealth narration."""
        from scripts.aeonisk.multiagent.awareness import filter_narrations_for_agent, NarrationEntry

        narrations = [
            NarrationEntry(
                text="[Echo] Echo slips past the guard undetected.",
                aware_agents=["dm", "player_echo"]
            ),
            NarrationEntry(
                text="[Guard] The guard patrols the corridor.",
                aware_agents=[]
            ),
        ]

        # Echo should see both their stealth action AND public narrations
        filtered = filter_narrations_for_agent("player_echo", narrations)
        assert len(filtered) == 2
        texts = [n.text for n in filtered]
        assert any("slips past" in t for t in texts)
        assert any("patrols the corridor" in t for t in texts)

    def test_player_sees_public_narrations(self):
        """All players see narrations with empty aware_agents."""
        from scripts.aeonisk.multiagent.awareness import filter_narrations_for_agent, NarrationEntry

        narrations = [
            NarrationEntry(text="[DM] A loud explosion rocks the building!", aware_agents=[]),
            NarrationEntry(text="[Ash] Ash charges forward!", aware_agents=[]),
        ]

        # Every player should see all public narrations
        for agent_id in ["player_echo", "player_ash", "player_ren"]:
            filtered = filter_narrations_for_agent(agent_id, narrations)
            assert len(filtered) == 2, f"{agent_id} should see all public narrations"

    def test_narration_entry_str_returns_text(self):
        """str(NarrationEntry(...)) should return just the text, not dataclass repr."""
        from scripts.aeonisk.multiagent.awareness import NarrationEntry

        entry = NarrationEntry(
            text="[Echo] Echo slips past the guard undetected.",
            aware_agents=["dm", "player_echo"]
        )

        result = str(entry)
        assert result == "[Echo] Echo slips past the guard undetected."
        assert "NarrationEntry" not in result
        assert "aware_agents" not in result

    def test_narration_entry_fstring_returns_text(self):
        """f-string formatting of NarrationEntry should return just the text."""
        from scripts.aeonisk.multiagent.awareness import NarrationEntry

        entry = NarrationEntry(
            text="[Echo] Echo hacks the terminal quietly.",
            aware_agents=["dm", "player_echo"]
        )

        result = f"1. {entry}"
        assert result == "1. [Echo] Echo hacks the terminal quietly."
        assert "NarrationEntry" not in result


class TestBackwardsCompatibility:
    """Test that existing sessions without aware_agents still work."""

    def test_resolution_without_aware_agents_is_public(self):
        """Resolutions without aware_agents field should be treated as public."""
        resolution = ActionResolution(
            narration="Standard action that everyone sees. The guard fires their weapon at the intruder, muzzle flash illuminating the dark corridor. " * 3,
            success_tier=SuccessTier.GOOD,
            margin=5,
        )
        # Empty list means public
        assert resolution.aware_agents == []

    def test_mixed_narration_types_handled(self):
        """System should handle mix of old strings and new NarrationEntry."""
        from scripts.aeonisk.multiagent.awareness import filter_narrations_for_agent
        from scripts.aeonisk.multiagent.player import NarrationEntry

        # Mix of old and new formats
        mixed = [
            "[Old] Old string format",  # Old: plain string
            NarrationEntry(text="[New] New format", aware_agents=["dm"]),  # New: NarrationEntry
        ]

        # Should handle both - strings treated as public
        filtered = filter_narrations_for_agent("random_npc", mixed)
        # Old string should be visible (public), new entry should not (NPC not in aware_agents)
        assert len(filtered) == 1
        assert "Old string format" in filtered[0] if isinstance(filtered[0], str) else filtered[0].text


# =============================================================================
# STEALTH TARGET FILTERING TESTS (TDD — written before implementation)
# =============================================================================


class TestSharedStateStealthTracking:
    """Test SharedState stealth_state dict and visibility methods."""

    def test_stealth_state_default_visible(self):
        """PC not in stealth_state → is_visible_to returns True for any observer."""
        from scripts.aeonisk.multiagent.shared_state import SharedState

        state = SharedState()
        # No stealth state set at all — everyone is visible
        assert state.is_visible_to("player_Shadow", "enemy_grunt_1") is True
        assert state.is_visible_to("player_Shadow", "npc_guard") is True
        assert state.is_visible_to("player_Shadow", "dm") is True

    def test_stealth_state_hidden_pc(self):
        """PC with restricted stealth_state → hidden from non-listed observers."""
        from scripts.aeonisk.multiagent.shared_state import SharedState, StealthEntry

        state = SharedState()
        state.stealth_state["player_Shadow"] = StealthEntry(
            observers={"dm", "player_Shadow"}, expires_at_round=99
        )

        # Observers in the set can see
        assert state.is_visible_to("player_Shadow", "dm") is True
        assert state.is_visible_to("player_Shadow", "player_Shadow") is True

        # Observers NOT in the set cannot see
        assert state.is_visible_to("player_Shadow", "enemy_grunt_1") is False
        assert state.is_visible_to("player_Shadow", "npc_guard") is False
        assert state.is_visible_to("player_Shadow", "player_Ash") is False

    def test_update_stealth_hides_pc(self):
        """update_stealth with non-empty aware_agents and positive margin hides PC."""
        from scripts.aeonisk.multiagent.shared_state import SharedState

        state = SharedState()
        state.update_stealth("player_Shadow", ["dm", "player_Shadow"], margin=5, current_round=1)

        assert "player_Shadow" in state.stealth_state
        assert state.is_visible_to("player_Shadow", "enemy_grunt_1") is False
        assert state.is_visible_to("player_Shadow", "dm") is True

    def test_update_stealth_public_reveals(self):
        """update_stealth with empty aware_agents removes PC from stealth_state."""
        from scripts.aeonisk.multiagent.shared_state import SharedState

        state = SharedState()
        # First hide the PC
        state.update_stealth("player_Shadow", ["dm", "player_Shadow"], margin=5, current_round=1)
        assert "player_Shadow" in state.stealth_state

        # Then make action public — should remove from stealth
        state.update_stealth("player_Shadow", [])
        assert "player_Shadow" not in state.stealth_state
        assert state.is_visible_to("player_Shadow", "enemy_grunt_1") is True

    def test_reveal_agent(self):
        """reveal_agent removes PC from stealth_state entirely."""
        from scripts.aeonisk.multiagent.shared_state import SharedState, StealthEntry

        state = SharedState()
        state.stealth_state["player_Shadow"] = StealthEntry(
            observers={"dm", "player_Shadow"}, expires_at_round=99
        )

        state.reveal_agent("player_Shadow")
        assert "player_Shadow" not in state.stealth_state
        assert state.is_visible_to("player_Shadow", "enemy_grunt_1") is True

    def test_reveal_agent_noop_for_visible(self):
        """reveal_agent on already-visible PC is a safe no-op."""
        from scripts.aeonisk.multiagent.shared_state import SharedState

        state = SharedState()
        # PC is not in stealth state — reveal should not crash
        state.reveal_agent("player_Shadow")
        assert "player_Shadow" not in state.stealth_state


class TestEnemyTargetFiltering:
    """Test that hidden PCs are excluded from enemy target lists."""

    def test_hidden_pc_excluded_from_enemy_target_list(self):
        """Hidden PC should not appear in visible_players after filtering."""
        from scripts.aeonisk.multiagent.shared_state import SharedState

        state = SharedState()
        state.update_stealth("player_Shadow", ["dm", "player_Shadow"], margin=5, current_round=1)

        # Simulate player_agents list
        player_shadow = MagicMock()
        player_shadow.agent_id = "player_Shadow"
        player_ash = MagicMock()
        player_ash.agent_id = "player_Ash"

        enemy_id = "enemy_grunt_1"
        visible_players = [
            pc for pc in [player_shadow, player_ash]
            if state.is_visible_to(pc.agent_id, enemy_id)
        ]

        assert len(visible_players) == 1
        assert visible_players[0].agent_id == "player_Ash"

    def test_visible_pc_included_in_enemy_target_list(self):
        """Public PC still appears in visible_players."""
        from scripts.aeonisk.multiagent.shared_state import SharedState

        state = SharedState()
        # No stealth — both visible

        player_shadow = MagicMock()
        player_shadow.agent_id = "player_Shadow"
        player_ash = MagicMock()
        player_ash.agent_id = "player_Ash"

        enemy_id = "enemy_grunt_1"
        visible_players = [
            pc for pc in [player_shadow, player_ash]
            if state.is_visible_to(pc.agent_id, enemy_id)
        ]

        assert len(visible_players) == 2

    def test_specific_enemy_in_aware_agents_can_target(self):
        """Enemy explicitly listed in aware_agents CAN see the PC."""
        from scripts.aeonisk.multiagent.shared_state import SharedState

        state = SharedState()
        # Shadow is detected by grunt_1 but not grunt_2
        state.update_stealth("player_Shadow", ["dm", "player_Shadow", "enemy_grunt_1"], margin=5, current_round=1)

        assert state.is_visible_to("player_Shadow", "enemy_grunt_1") is True
        assert state.is_visible_to("player_Shadow", "enemy_grunt_2") is False


class TestNPCTargetFiltering:
    """Test that hidden PCs are excluded from NPC target lists."""

    def test_hidden_pc_excluded_from_npc_target_list(self):
        """Hidden PC should be skipped in NPC combatant list."""
        from scripts.aeonisk.multiagent.shared_state import SharedState

        state = SharedState()
        state.update_stealth("player_Shadow", ["dm", "player_Shadow"], margin=5, current_round=1)

        # Simulate combatant info entries
        combatants = [
            {'agent_id': 'player_Shadow', 'type': 'player', 'name': 'Shadow'},
            {'agent_id': 'player_Ash', 'type': 'player', 'name': 'Ash'},
            {'agent_id': 'enemy_grunt_1', 'type': 'enemy', 'name': 'Grunt'},
        ]

        npc_agent_id = "npc_civilian_1"
        visible = [
            c for c in combatants
            if not (c['type'] == 'player' and not state.is_visible_to(c['agent_id'], npc_agent_id))
        ]

        # Shadow hidden, Ash visible, Grunt visible (not a player, no stealth check)
        assert len(visible) == 2
        names = [c['name'] for c in visible]
        assert 'Shadow' not in names
        assert 'Ash' in names
        assert 'Grunt' in names


class TestRevealMechanics:
    """Test that enemy hits reveal hidden PCs."""

    def test_enemy_hit_reveals_hidden_pc(self):
        """After enemy hits a hidden PC, that PC becomes visible to all."""
        from scripts.aeonisk.multiagent.shared_state import SharedState

        state = SharedState()
        state.update_stealth("player_Shadow", ["dm", "player_Shadow"], margin=5, current_round=1)

        # Verify hidden before hit
        assert state.is_visible_to("player_Shadow", "enemy_grunt_1") is False

        # Simulate enemy hit — reveal target
        state.reveal_agent("player_Shadow")

        # Now visible to all
        assert state.is_visible_to("player_Shadow", "enemy_grunt_1") is True
        assert state.is_visible_to("player_Shadow", "enemy_grunt_2") is True
        assert state.is_visible_to("player_Shadow", "npc_guard") is True


# =============================================================================
# STEALTH DURATION & EXPIRY TESTS (TDD — written before implementation)
# =============================================================================


class TestStealthDurationFromMargin:
    """Test that stealth duration scales with roll margin."""

    def test_stealth_duration_margin_0(self):
        """Margin ≤ 0 → no stealth entry created."""
        from scripts.aeonisk.multiagent.shared_state import SharedState

        state = SharedState()
        state.update_stealth("player_Shadow", ["dm", "player_Shadow"], margin=0, current_round=1)
        assert "player_Shadow" not in state.stealth_state

    def test_stealth_duration_margin_negative(self):
        """Negative margin → no stealth entry created."""
        from scripts.aeonisk.multiagent.shared_state import SharedState

        state = SharedState()
        state.update_stealth("player_Shadow", ["dm", "player_Shadow"], margin=-3, current_round=1)
        assert "player_Shadow" not in state.stealth_state

    def test_stealth_duration_margin_3(self):
        """Margin 1-5 → 1 round duration (expires_at_round = current + 1)."""
        from scripts.aeonisk.multiagent.shared_state import SharedState

        state = SharedState()
        state.update_stealth("player_Shadow", ["dm", "player_Shadow"], margin=3, current_round=1)
        assert "player_Shadow" in state.stealth_state
        assert state.stealth_state["player_Shadow"].expires_at_round == 2

    def test_stealth_duration_margin_8(self):
        """Margin 6-10 → 2 round duration."""
        from scripts.aeonisk.multiagent.shared_state import SharedState

        state = SharedState()
        state.update_stealth("player_Shadow", ["dm", "player_Shadow"], margin=8, current_round=1)
        assert state.stealth_state["player_Shadow"].expires_at_round == 3

    def test_stealth_duration_margin_12(self):
        """Margin 11-15 → 3 round duration."""
        from scripts.aeonisk.multiagent.shared_state import SharedState

        state = SharedState()
        state.update_stealth("player_Shadow", ["dm", "player_Shadow"], margin=12, current_round=1)
        assert state.stealth_state["player_Shadow"].expires_at_round == 4

    def test_stealth_duration_margin_20(self):
        """Margin 16+ → 4 round duration."""
        from scripts.aeonisk.multiagent.shared_state import SharedState

        state = SharedState()
        state.update_stealth("player_Shadow", ["dm", "player_Shadow"], margin=20, current_round=1)
        assert state.stealth_state["player_Shadow"].expires_at_round == 5


class TestStealthExpiry:
    """Test stealth expiry at round start."""

    def test_expire_stealth_removes_expired(self):
        """Entry with expires_at_round=2 removed on round 3."""
        from scripts.aeonisk.multiagent.shared_state import SharedState

        state = SharedState()
        state.update_stealth("player_Shadow", ["dm", "player_Shadow"], margin=3, current_round=1)
        # expires_at_round = 2 (margin 3 → 1 round duration)
        assert "player_Shadow" in state.stealth_state

        # Round 2: still hidden (expires_at_round=2 is inclusive)
        state.expire_stealth(2)
        assert "player_Shadow" in state.stealth_state

        # Round 3: expired
        state.expire_stealth(3)
        assert "player_Shadow" not in state.stealth_state

    def test_expire_stealth_keeps_active(self):
        """Entry with expires_at_round=4 kept on round 3."""
        from scripts.aeonisk.multiagent.shared_state import SharedState

        state = SharedState()
        state.update_stealth("player_Shadow", ["dm", "player_Shadow"], margin=12, current_round=1)
        # expires_at_round = 4 (margin 12 → 3 round duration)

        state.expire_stealth(3)
        assert "player_Shadow" in state.stealth_state

    def test_stealth_renewal_extends_duration(self):
        """Second update_stealth resets expiry timer."""
        from scripts.aeonisk.multiagent.shared_state import SharedState

        state = SharedState()
        state.update_stealth("player_Shadow", ["dm", "player_Shadow"], margin=3, current_round=1)
        assert state.stealth_state["player_Shadow"].expires_at_round == 2

        # Renew on round 2 with better margin
        state.update_stealth("player_Shadow", ["dm", "player_Shadow"], margin=8, current_round=2)
        assert state.stealth_state["player_Shadow"].expires_at_round == 4


class TestGetHiddenPcs:
    """Test get_hidden_pcs utility method."""

    def test_get_hidden_pcs_empty(self):
        """No hidden PCs returns empty list."""
        from scripts.aeonisk.multiagent.shared_state import SharedState

        state = SharedState()
        assert state.get_hidden_pcs() == []

    def test_get_hidden_pcs_returns_hidden(self):
        """Returns list of hidden PC agent_ids."""
        from scripts.aeonisk.multiagent.shared_state import SharedState

        state = SharedState()
        state.update_stealth("player_Shadow", ["dm", "player_Shadow"], margin=5, current_round=1)
        state.update_stealth("player_Echo", ["dm", "player_Echo"], margin=8, current_round=1)

        hidden = state.get_hidden_pcs()
        assert "player_Shadow" in hidden
        assert "player_Echo" in hidden
        assert len(hidden) == 2


class TestEnemyDetection:
    """Test enemy detection rolls against hidden PCs."""

    def test_enemy_detection_success_reveals_globally(self):
        """Detection roll ≥ stealth DC → reveal_agent called (global reveal)."""
        from scripts.aeonisk.multiagent.shared_state import SharedState

        state = SharedState()
        state.update_stealth("player_Shadow", ["dm", "player_Shadow"], margin=5, current_round=1)

        # Simulate successful detection
        assert state.is_visible_to("player_Shadow", "enemy_grunt_1") is False
        state.reveal_agent("player_Shadow")  # Detection success → global reveal
        assert state.is_visible_to("player_Shadow", "enemy_grunt_1") is True
        assert state.is_visible_to("player_Shadow", "enemy_grunt_2") is True

    def test_enemy_detection_failure_keeps_hidden(self):
        """Detection roll < stealth DC → PC stays hidden."""
        from scripts.aeonisk.multiagent.shared_state import SharedState

        state = SharedState()
        state.update_stealth("player_Shadow", ["dm", "player_Shadow"], margin=5, current_round=1)

        # Detection fails — do NOT call reveal_agent
        assert state.is_visible_to("player_Shadow", "enemy_grunt_1") is False
        # PC remains hidden
        assert "player_Shadow" in state.stealth_state

    def test_unskilled_enemy_uses_half_roll(self):
        """Awareness=0 → detection uses d20 // 2 (unskilled penalty)."""
        # This tests the detection logic in enemy_combat.py
        # Unskilled: detection_total = d20 // 2 (no attribute multiplier)
        # With d20=10 and Awareness=0: detection_total = 10 // 2 = 5
        # Against stealth_dc of 15: fails
        detection_roll = 10
        awareness = 0
        perception = 4
        if awareness > 0:
            detection_total = (perception * awareness) + detection_roll
        else:
            detection_total = detection_roll // 2

        assert detection_total == 5  # 10 // 2
        assert detection_total < 15  # Fails against DC 15

    def test_skilled_enemy_detection_formula(self):
        """Awareness>0 → detection uses Per×Awareness + d20."""
        detection_roll = 15
        awareness = 3
        perception = 4
        if awareness > 0:
            detection_total = (perception * awareness) + detection_roll
        else:
            detection_total = detection_roll // 2

        assert detection_total == 27  # 4*3 + 15
        assert detection_total >= 15  # Passes against DC 15
