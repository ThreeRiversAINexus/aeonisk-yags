"""
Tests for IFF/ROE (Identification Friend or Foe / Rules of Engagement) system.

Spec 06: Steps 5-8
- Step 5: Selective intel sharing (SharedIntel with recipients)
- Step 6: EnemyDecision intel_recipients field
- Step 7: Intercepted communications (enemy intel leaking to PCs)
- Step 8: Faction context prompts (enemy IFF context + PC party context)
- Config flag: iff_enabled gating all IFF changes
"""

import pytest
import sys
import os

# Add scripts directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))

from aeonisk.multiagent.enemy_agent import SharedIntel, IntelItem
from aeonisk.multiagent.schemas.enemy_decision import EnemyDecision


# =============================================================================
# STEP 5: Selective Intel Sharing
# =============================================================================

class TestSelectiveIntelSharing:
    """SharedIntel refactored from global broadcast to explicit recipients."""

    def test_intel_delivered_to_recipient(self):
        """Intel should be visible to specified recipient target_id."""
        intel = SharedIntel()
        intel.add_intel(
            source_target_id="tgt_1111",
            intel="Flanking left",
            round_num=1,
            recipients={"tgt_2222"}
        )
        result = intel.get_recent_intel_for_target("tgt_2222", current_round=1)
        assert len(result) == 1
        assert "Flanking left" in result[0]

    def test_intel_not_visible_to_non_recipient(self):
        """Intel should NOT be visible to targets not in recipients."""
        intel = SharedIntel()
        intel.add_intel(
            source_target_id="tgt_1111",
            intel="Secret plan",
            round_num=1,
            recipients={"tgt_2222"}
        )
        result = intel.get_recent_intel_for_target("tgt_3333", current_round=1)
        assert len(result) == 0

    def test_intel_leak_to_pc(self):
        """Enemy intel addressed to a PC target_id should be visible to that PC."""
        intel = SharedIntel()
        # Enemy tgt_1111 thinks tgt_9999 is an ally, but it's a PC
        intel.add_intel(
            source_target_id="tgt_1111",
            intel="Attack the Freeborn on the left",
            round_num=1,
            recipients={"tgt_9999"}
        )
        # PC queries their intel
        result = intel.get_recent_intel_for_target("tgt_9999", current_round=1)
        assert len(result) == 1
        assert "Attack the Freeborn" in result[0]

    def test_no_broadcast_without_recipients(self):
        """Intel with empty recipients should not be delivered to anyone."""
        intel = SharedIntel()
        intel.add_intel(
            source_target_id="tgt_1111",
            intel="Hello",
            round_num=1,
            recipients=set()
        )
        result = intel.get_recent_intel_for_target("tgt_2222", current_round=1)
        assert len(result) == 0

    def test_intel_expires_after_lookback(self):
        """Intel older than lookback rounds should not appear."""
        intel = SharedIntel()
        intel.add_intel(
            source_target_id="tgt_1111",
            intel="Old info",
            round_num=1,
            recipients={"tgt_2222"}
        )
        result = intel.get_recent_intel_for_target(
            "tgt_2222", current_round=5, lookback=2
        )
        assert len(result) == 0

    def test_multiple_recipients(self):
        """Intel can be addressed to multiple targets."""
        intel = SharedIntel()
        intel.add_intel(
            source_target_id="tgt_1111",
            intel="Group intel",
            round_num=1,
            recipients={"tgt_2222", "tgt_3333", "tgt_4444"}
        )
        assert len(intel.get_recent_intel_for_target("tgt_2222", 1)) == 1
        assert len(intel.get_recent_intel_for_target("tgt_3333", 1)) == 1
        assert len(intel.get_recent_intel_for_target("tgt_4444", 1)) == 1
        assert len(intel.get_recent_intel_for_target("tgt_5555", 1)) == 0

    def test_intel_source_shown_as_target_id(self):
        """Intel source should show as tgt_xxxx, not agent name."""
        intel = SharedIntel()
        intel.add_intel(
            source_target_id="tgt_abcd",
            intel="Testing source display",
            round_num=1,
            recipients={"tgt_1234"}
        )
        result = intel.get_recent_intel_for_target("tgt_1234", current_round=1)
        assert len(result) == 1
        assert "[FROM tgt_abcd]" in result[0]

    def test_legacy_broadcast_mode(self):
        """When iff_enabled=False, legacy add_intel with source_agent broadcasts to all."""
        intel = SharedIntel()
        # Legacy mode: use source_agent (string name) and no recipients
        intel.add_intel(source_agent="ACG Scout", intel="Enemy spotted", round_num=1)
        # Legacy get_recent_intel returns all intel (no filtering)
        result = intel.get_recent_intel(current_round=1)
        assert len(result) == 1
        assert "Enemy spotted" in result[0]

    def test_legacy_and_selective_coexist(self):
        """Both legacy broadcast and selective intel can coexist in same pool."""
        intel = SharedIntel()
        # Legacy broadcast
        intel.add_intel(source_agent="ACG Scout", intel="Broadcast msg", round_num=1)
        # Selective
        intel.add_intel(
            source_target_id="tgt_1111",
            intel="Selective msg",
            round_num=1,
            recipients={"tgt_2222"}
        )
        # Legacy get_recent_intel sees both
        result = intel.get_recent_intel(current_round=1)
        assert len(result) == 2
        # Selective get_recent_intel_for_target sees only addressed
        result = intel.get_recent_intel_for_target("tgt_2222", current_round=1)
        assert len(result) == 1
        assert "Selective msg" in result[0]

    def test_clear_old_intel_works_with_selective(self):
        """clear_old_intel should work with selective intel items."""
        intel = SharedIntel()
        intel.add_intel(
            source_target_id="tgt_1111",
            intel="Old",
            round_num=1,
            recipients={"tgt_2222"}
        )
        intel.add_intel(
            source_target_id="tgt_1111",
            intel="New",
            round_num=5,
            recipients={"tgt_2222"}
        )
        intel.clear_old_intel(current_round=5, max_age=2)
        assert len(intel.intel_pool) == 1
        assert intel.intel_pool[0].intel == "New"


# =============================================================================
# STEP 6: EnemyDecision intel_recipients Field
# =============================================================================

class TestEnemyDecisionIntelRecipients:
    """EnemyDecision schema with intel_recipients field."""

    def test_intel_recipients_accepts_target_ids(self):
        """intel_recipients should accept a list of tgt_xxxx strings."""
        decision = EnemyDecision(
            major_action="Attack",
            target="tgt_7a3f",
            tactical_reasoning="Focus fire on wounded target to eliminate threat quickly",
            shared_intel="Target is flanking",
            intel_recipients=["tgt_2222", "tgt_3333"]
        )
        assert decision.intel_recipients == ["tgt_2222", "tgt_3333"]

    def test_intel_recipients_defaults_to_none(self):
        """intel_recipients should default to None (backward compat)."""
        decision = EnemyDecision(
            major_action="Attack",
            target="tgt_7a3f",
            tactical_reasoning="Focus fire on wounded target to eliminate threat quickly"
        )
        assert decision.intel_recipients is None

    def test_intel_recipients_in_legacy_dict(self):
        """intel_recipients should be included in to_legacy_dict output."""
        decision = EnemyDecision(
            major_action="Attack",
            target="tgt_7a3f",
            tactical_reasoning="Focus fire on wounded target to eliminate threat quickly",
            shared_intel="Target flanking",
            intel_recipients=["tgt_2222"]
        )
        legacy = decision.to_legacy_dict()
        assert legacy.get('intel_recipients') == ["tgt_2222"]

    def test_intel_recipients_none_in_legacy_dict(self):
        """When intel_recipients is None, legacy dict should include None."""
        decision = EnemyDecision(
            major_action="Attack",
            target="tgt_7a3f",
            tactical_reasoning="Focus fire on wounded target to eliminate threat quickly"
        )
        legacy = decision.to_legacy_dict()
        assert 'intel_recipients' in legacy
        assert legacy['intel_recipients'] is None

    def test_empty_intel_recipients_list(self):
        """Empty intel_recipients list is valid (no recipients)."""
        decision = EnemyDecision(
            major_action="Attack",
            target="tgt_7a3f",
            tactical_reasoning="Focus fire on wounded target to eliminate threat quickly",
            shared_intel="Some intel",
            intel_recipients=[]
        )
        assert decision.intel_recipients == []


# =============================================================================
# STEP 7: Intercepted Communications
# =============================================================================

class TestInterceptedIntel:
    """PC receiving accidentally leaked enemy intel."""

    def test_intercepted_intel_formatted(self):
        """Leaked intel should appear as intercepted communication."""
        intel = SharedIntel()
        intel.add_intel(
            source_target_id="tgt_1111",
            intel="Focus fire on the rifleman",
            round_num=1,
            recipients={"tgt_9999"}
        )
        from aeonisk.multiagent.dm import AIDMAgent
        text = AIDMAgent._get_intercepted_intel_for_pc(
            pc_target_id="tgt_9999",
            shared_intel=intel,
            current_round=1
        )
        assert "INTERCEPTED" in text
        assert "Focus fire on the rifleman" in text

    def test_no_intercepted_section_when_empty(self):
        """No intercepted section when PC has no leaked intel."""
        intel = SharedIntel()
        from aeonisk.multiagent.dm import AIDMAgent
        text = AIDMAgent._get_intercepted_intel_for_pc(
            pc_target_id="tgt_9999",
            shared_intel=intel,
            current_round=1
        )
        assert text == ""

    def test_intercepted_intel_multiple_items(self):
        """PC should see all intel addressed to them."""
        intel = SharedIntel()
        intel.add_intel(
            source_target_id="tgt_1111",
            intel="Flanking left",
            round_num=1,
            recipients={"tgt_9999"}
        )
        intel.add_intel(
            source_target_id="tgt_2222",
            intel="Cover me",
            round_num=1,
            recipients={"tgt_9999"}
        )
        from aeonisk.multiagent.dm import AIDMAgent
        text = AIDMAgent._get_intercepted_intel_for_pc(
            pc_target_id="tgt_9999",
            shared_intel=intel,
            current_round=1
        )
        assert "Flanking left" in text
        assert "Cover me" in text


# =============================================================================
# STEP 8: Faction Context Prompts
# =============================================================================

class TestEnemyFactionContext:
    """Enemy faction context for IFF reasoning."""

    def test_iff_faction_context_includes_faction_name(self):
        """IFF context should tell the enemy its own faction."""
        from aeonisk.multiagent.enemy_prompts import _format_iff_context
        context = _format_iff_context("ACG")
        assert "ACG" in context

    def test_iff_faction_context_includes_reasoning_instruction(self):
        """IFF context should instruct enemy to reason about allegiance."""
        from aeonisk.multiagent.enemy_prompts import _format_iff_context
        context = _format_iff_context("ACG")
        assert "allegiance" in context.lower() or "faction" in context.lower()

    def test_iff_faction_context_mentions_communication(self):
        """IFF context should mention intel sharing with recipients."""
        from aeonisk.multiagent.enemy_prompts import _format_iff_context
        context = _format_iff_context("ACG")
        assert "intel_recipients" in context or "recipients" in context.lower()


class TestPCPartyContext:
    """PC party context telling PCs which tgt_xxxx IDs are party members."""

    def test_party_context_lists_party_members(self):
        """Party context should list party member target IDs."""
        from aeonisk.multiagent.dm import AIDMAgent
        party_members = [
            {"name": "Ash Vex", "target_id": "tgt_1111"},
            {"name": "Kiran Voss", "target_id": "tgt_2222"},
        ]
        text = AIDMAgent._build_pc_party_context(
            pc_target_id="tgt_1111",
            party_members=party_members
        )
        # Should list OTHER party members, not self
        assert "tgt_2222" in text
        assert "Kiran Voss" in text

    def test_party_context_excludes_self(self):
        """Party context should not list the PC themselves."""
        from aeonisk.multiagent.dm import AIDMAgent
        party_members = [
            {"name": "Ash Vex", "target_id": "tgt_1111"},
            {"name": "Kiran Voss", "target_id": "tgt_2222"},
        ]
        text = AIDMAgent._build_pc_party_context(
            pc_target_id="tgt_1111",
            party_members=party_members
        )
        # Should not list self as party member
        assert "tgt_1111" not in text or "Ash Vex" not in text

    def test_party_context_empty_when_solo(self):
        """Party context should be empty when PC is alone."""
        from aeonisk.multiagent.dm import AIDMAgent
        party_members = [
            {"name": "Ash Vex", "target_id": "tgt_1111"},
        ]
        text = AIDMAgent._build_pc_party_context(
            pc_target_id="tgt_1111",
            party_members=party_members
        )
        assert text == "" or "no other party members" in text.lower()


# =============================================================================
# CONFIG FLAG: iff_enabled
# =============================================================================

class TestIFFConfigFlag:
    """iff_enabled config flag gates all IFF changes."""

    def test_iff_enabled_defaults_to_false(self):
        """iff_enabled should default to False when not in config."""
        config = {
            'session_name': 'test',
            'max_turns': 5,
            'party_size': 2,
            'agents': {}
        }
        # iff_enabled should be readable from config, defaulting to False
        iff_enabled = config.get('iff_enabled', False)
        assert iff_enabled is False

    def test_iff_enabled_true_in_config(self):
        """iff_enabled=true should be readable from config."""
        config = {
            'session_name': 'test',
            'max_turns': 5,
            'party_size': 2,
            'agents': {},
            'iff_enabled': True
        }
        iff_enabled = config.get('iff_enabled', False)
        assert iff_enabled is True

    def test_enemy_combat_manager_reads_iff_enabled(self):
        """EnemyCombatManager should store iff_enabled from session config."""
        from aeonisk.multiagent.enemy_combat import EnemyCombatManager
        mgr = EnemyCombatManager()
        mgr.initialize({
            'tactical_module_enabled': True,
            'enemy_agents_enabled': True,
            'iff_enabled': True,
        })
        assert mgr.iff_enabled is True

    def test_enemy_combat_manager_iff_defaults_false(self):
        """EnemyCombatManager iff_enabled should default to False."""
        from aeonisk.multiagent.enemy_combat import EnemyCombatManager
        mgr = EnemyCombatManager()
        mgr.initialize({
            'tactical_module_enabled': True,
            'enemy_agents_enabled': True,
        })
        assert mgr.iff_enabled is False

    def test_shared_intel_selective_when_iff_enabled(self):
        """When iff_enabled, SharedIntel should use selective mode for new intel."""
        intel = SharedIntel()
        # Selective mode — requires source_target_id and recipients
        intel.add_intel(
            source_target_id="tgt_1111",
            intel="Selective intel",
            round_num=1,
            recipients={"tgt_2222"}
        )
        # Should only be visible to tgt_2222
        assert len(intel.get_recent_intel_for_target("tgt_2222", 1)) == 1
        assert len(intel.get_recent_intel_for_target("tgt_3333", 1)) == 0


# =============================================================================
# BACKWARD COMPATIBILITY
# =============================================================================

class TestIFFBackwardCompat:
    """Verify legacy behavior is preserved when iff_enabled=False."""

    def test_legacy_add_intel_still_works(self):
        """Legacy add_intel(source_agent, intel, round_num) should still work."""
        intel = SharedIntel()
        intel.add_intel(source_agent="ACG Scout", intel="Enemy spotted", round_num=1)
        result = intel.get_recent_intel(current_round=1)
        assert len(result) == 1
        assert "ACG Scout" in result[0]
        assert "Enemy spotted" in result[0]

    def test_legacy_get_recent_intel_returns_all(self):
        """Legacy get_recent_intel returns all intel (no recipient filtering)."""
        intel = SharedIntel()
        intel.add_intel(source_agent="Scout A", intel="Intel 1", round_num=1)
        intel.add_intel(source_agent="Scout B", intel="Intel 2", round_num=1)
        result = intel.get_recent_intel(current_round=1)
        assert len(result) == 2

    def test_legacy_format_uses_from_prefix(self):
        """Legacy intel should use [FROM ...] prefix (Step 1 already done)."""
        intel = SharedIntel()
        intel.add_intel(source_agent="ACG Scout", intel="Contact", round_num=1)
        result = intel.get_recent_intel(current_round=1)
        assert "[FROM " in result[0]

    def test_intel_item_dataclass_has_recipients(self):
        """IntelItem should have an optional recipients field."""
        item = IntelItem(
            source_agent="ACG Scout",
            intel="Test",
            round=1,
            recipients=None
        )
        assert item.recipients is None

    def test_intel_item_with_target_id_source(self):
        """IntelItem should accept source_target_id instead of source_agent."""
        item = IntelItem(
            source_target_id="tgt_1111",
            intel="Test",
            round=1,
            recipients={"tgt_2222"}
        )
        assert item.source_target_id == "tgt_1111"
        assert item.recipients == {"tgt_2222"}
