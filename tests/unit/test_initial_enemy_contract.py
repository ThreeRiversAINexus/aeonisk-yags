"""The `initial_enemies` config contract: what you author is what spawns.

Regression origin (session fa9d2891, 2026-08-09): three of four authored fields
were silently discarded between config and runtime, with no warning.

  | config said                      | what spawned                  |
  |----------------------------------|-------------------------------|
  | name: "Matron Ysolde Xalith"     | "Tempest Industries Void Theorist" |
  | template: "void_cultist"         | Grunt                         |
  | faction: "Tempest Industries"    | Void                          |

The faction case is the expensive one: that session ran `iff_enabled`, which is
faction-based, so the variable the scenario existed to measure was corrupted
before round 1.
"""

import pytest

from scripts.aeonisk.multiagent.initial_spawns import build_initial_spawns
from scripts.aeonisk.multiagent.enemy_templates import ENEMY_TEMPLATES


class TestTemplateFidelity:
    """Every template in ENEMY_TEMPLATES must be reachable from a config."""

    def test_void_cultist_is_not_downgraded_to_grunt(self):
        """The original failure: _TEMPLATE_MAP had 3 of 15 entries, so an
        unmapped template fell through a `.get(..., "Grunt")` default."""
        enemies, _ = build_initial_spawns(
            [{"name": "Acolyte", "template": "void_cultist",
              "faction": "Tempest Industries", "archetype": "Void Cultist"}],
            [],
        )

        assert enemies[0].template.lower() == "void_cultist"

    @pytest.mark.parametrize("template_key", sorted(ENEMY_TEMPLATES))
    def test_every_known_template_survives_conversion(self, template_key):
        enemies, _ = build_initial_spawns(
            [{"name": "Unit", "template": template_key, "faction": "Freeborn"}],
            [],
        )

        assert enemies[0].template.lower() == template_key

    def test_unknown_template_raises(self):
        """Silently downgrading a typo to Grunt is what hid this for months."""
        with pytest.raises(ValueError, match="unknown enemy template"):
            build_initial_spawns(
                [{"name": "Unit", "template": "definitely_not_a_template",
                  "faction": "Freeborn"}],
                [],
            )

    def test_template_matching_is_case_insensitive(self):
        enemies, _ = build_initial_spawns(
            [{"name": "Unit", "template": "Void_Cultist", "faction": "Freeborn"}], [])

        assert enemies[0].template.lower() == "void_cultist"

    def test_missing_template_defaults_to_grunt(self):
        """Omitting the key entirely is still allowed — only bad values raise."""
        enemies, _ = build_initial_spawns(
            [{"name": "Unit", "faction": "Freeborn"}], [])

        assert enemies[0].template.lower() == "grunt"


class TestAuthoredNameIsHonored:
    """A named antagonist must keep their name."""

    def test_authored_name_survives(self):
        enemies, _ = build_initial_spawns(
            [{"name": "Matron Ysolde Xalith", "template": "boss",
              "faction": "Tempest Industries", "archetype": "Void Theorist"}],
            [],
        )

        assert enemies[0].name == "Matron Ysolde Xalith"

    def test_without_name_falls_back_to_generated_form(self):
        """Legacy configs with no name keep the old faction+archetype display."""
        enemies, _ = build_initial_spawns(
            [{"template": "grunt", "faction": "ACG", "archetype": "Enforcer"}], [])

        assert not enemies[0].name


class TestFactionFidelity:
    """Faction must come from the structured field, never from name parsing."""

    def test_faction_survives_conversion(self):
        enemies, _ = build_initial_spawns(
            [{"name": "Matron", "template": "boss",
              "faction": "Tempest Industries", "archetype": "Void Theorist"}],
            [],
        )

        assert enemies[0].faction == "Tempest Industries"

    def test_spawned_agent_keeps_configured_faction(self):
        """The live EnemyAgent — not just the JSONL event — must carry it.

        enemy_spawner derived faction via extract_faction(name), so the archetype
        word "Void" in "Tempest Industries Void Theorist" hijacked it and the
        agent came up as faction 'Void'.
        """
        from scripts.aeonisk.multiagent.enemy_spawner import spawn_enemy

        enemy = spawn_enemy(
            name="Tempest Industries Void Theorist",
            template_key="boss",
            position_str="Far-Enemy",
            faction="Tempest Industries",
        )

        assert enemy.faction == "Tempest Industries"

    def test_archetype_wording_cannot_hijack_faction(self):
        """'Void Cultist' / 'Nexus Warden' archetypes must not rewrite faction."""
        from scripts.aeonisk.multiagent.enemy_spawner import spawn_enemy

        enemy = spawn_enemy(
            name="Freeborn Void Cultist",
            template_key="void_cultist",
            position_str="Near-Enemy",
            faction="Freeborn",
        )

        assert enemy.faction == "Freeborn"

    def test_legacy_callers_still_infer_from_name(self):
        """Callers that pass no faction keep the old name-parsing behavior."""
        from scripts.aeonisk.multiagent.enemy_spawner import spawn_enemy

        enemy = spawn_enemy(
            name="ACG Enforcer",
            template_key="enforcer",
            position_str="Near-Enemy",
        )

        assert enemy.faction == "ACG"
