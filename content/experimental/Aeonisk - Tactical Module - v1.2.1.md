# Aeonisk Tactical Module - v1.2.1

**Integrating the Aeonisk Tactical Layer with YAGS Core**

This document clarifies and summarizes the key rules introduced by the Aeonisk Tactical Addendum to the YAGS Core system, based on v1.2 and subsequent refinements discussed in the source material.

---

### Introduction for New Players (or Players New to Tactical Aeonisk)

Welcome! If you're used to tabletop RPGs like D&D, you'll find a lot that's familiar here: you still roll a d20 + your character's skills and stats, aim for a target number, track damage and defense, and work together to overcome challenges.

What Aeonisk Tactical does is offer a specific, structured way to handle combat encounters that moves away from counting squares on a grid. Instead, we use simple **Range Bands** (Engaged, Near, Far, Extreme) to handle distances – think of them as zones or areas on the battlefield. Movement becomes shifting between these zones, which is much faster than measuring.

We also add **Tactical Tokens** – physical markers on the table that represent key pieces of terrain or positional advantages (like good Cover or High Ground). You'll actively "claim" these and then "spend" them for a temporary bonus, making the environment a dynamic tool you can use.

The **Action Economy** (what you can do on your turn) uses familiar concepts like Major and Minor actions, similar to Action and Bonus actions in other games. Initiative still determines turn order, but we add phases for declaring actions *before* resolving them, adding a layer of tactical planning and reaction.

Finally, there's a unique **Defence Token** system. Instead of just having a static defense value, you'll actively choose *one* enemy each round to focus your defence against, gaining a specific bonus if they attack you. This adds a simple but meaningful tactical choice every round.

This system is designed to make tactical combat flow quickly, emphasize narrative positioning, and provide clear, impactful choices without getting bogged down in precise measurements. Dive into the rules below, and don't hesitate to ask questions as we play!

---

### Quick-Start Cheat-Sheet

*This sheet is a brief overview. Detailed explanations follow.*

**Core Task Roll**
*   **Formula:** Attribute × Skill + d20
*   **Difficulty:** 10 (easy) | 20 (moderate) | 30 (challenging)
*   **Success Levels:** Every +10 over target = +1 success tier 

**Initiative & Tempo**
1.  **Roll once at start:** Agility × 4 + d20 (Nat 1 ⇒ INIT 0) 
2.  **Speed bands:** Fast → Normal → Slow
3.  **Declare in ↑ INIT**, resolve in ↓ INIT (within speed bands)
4.  **Shock reduces INIT**, can reroll by forfeit turn (halved at INIT 0) 

**Round Structure**
1.  **Declare Phase:** In ascending Initiative order, players state their intended Major and Minor actions. No rolls are made or effects resolved in this phase. The Defence Token is allocated.
2.  **Fast Phase (Reactions):** In descending Initiative order, resolve Reactions like Parries, spending Tokens, or Bonded Defence.
3.  **Slow Phase (Major/Minor Actions):** In descending Initiative order, resolve all declared Major and Minor actions.
4.  **Cleanup Phase:** Resolve lingering effects, check Wounds/Stun, make morale checks.

**Actions per Turn**
| Type         | Count     | Notes                                                                |
|--------------|-----------|----------------------------------------------------------------------|
| **Major**    | 1         | Big moves: attacks, two-band shifts                                  |
| **Minor**    | 1         | Shift 1 Band, Reload, Claim/Swap Token, Overwatch Setup, Stand from Prone |
| **Free**     | Unlimited | Flavor narrations only: shout orders, drop an item (after you swapped it), quick emotive beats |
| **Reaction** | 1         | Interrupts during Fast Phase: Parry, Overwatch, Token spend, Bonded Defence |

**Damage & Wound Tracking**
*   **Damage Roll:** Strength + Weapon Bonus + d20
*   **Soak:** Subtract from damage.
*   **Wounds:** 1 Wound per hit ≥ Soak, +1 per full +5 damage over Soak.
*   **Fatal:** At 5 Wounds, make a Health check (Hea × 2 vs. DC 20 + 5 per extra Wound).
*   **Wound Ladder:** A printable “Wound ladder” tracker should be provided.

---

### 1. Initiative, Tempo, and Round Structure

*   **Rolling Initiative:** Re-roll (Agility × 4) + d20 at the **start of every round**.
    *   **Ties:** Break ties by the highest single Skill rank, then the highest governing Attribute.
    *   **Natural 1:** Results in Initiative 0 for the round (all skill checks halved, all actions are Slow).
*   **Shock:** Reduces current Initiative. Can forfeit turn to re-roll Initiative (Agility x 4 + d20), halved if current Initiative is 0. 
*   **Round Order:**
    1.  **Declare Phase:** In ascending Initiative order, players state their intended Major and Minor actions. No rolls are made or effects resolved. The Defence Token is allocated.
    2.  **Fast Phase (Reactions):** In descending Initiative order, resolve Reactions (Parry, Spend Token, Bonded Defence).
    3.  **Slow Phase (Major/Minor Actions):** In descending Initiative order, resolve all declared Major and Minor actions.
    4.  **Cleanup Phase:** Resolve lingering effects, check Wounds/Stun, make morale checks.

#### Tactical Interaction Example

The Initiative order within the Declare and Resolution phases is crucial, especially when multiple actors want to interact with the same resource or target.

*   **Scenario:** Two characters attempt to claim the same Cover Tactical Token in the Declare Phase.
*   **Actors:**
    *   Goblin: Initiative 12
    *   Alice: Initiative 28
*   **Declare Phase (Ascending Initiative):**
    1.  Goblin (Init 12) declares: "I will claim Cover."
    2.  Alice (Init 28) declares: "I will claim Cover."
*   **Action Resolution Phase (Descending Initiative):**
    *   Claiming a token is a Minor Action (Normal Speed).
    *   Normal Speed Actions resolve in descending Initiative order.
    1.  Alice's Normal Action (Claim Cover) resolves first because she has higher Initiative (28 vs 12). Alice successfully claims the Cover token.
    2.  The Goblin's Normal Action (Claim Cover) resolves next. Since the token has already been claimed by Alice, the Goblin's action fails to secure *that specific token*. The Goblin player must either narrate an alternate outcome (e.g., trying to find *different* cover, or realizing it was taken) or their action is simply ineffective for that token this round. 

This example demonstrates how higher Initiative provides a tactical advantage by allowing actions to resolve sooner, potentially preventing slower actors from achieving their declared goals.

### 2. Action Economy

Each round, characters typically have:

*   **Major Action (1):** Complex actions (Attack, Shift 2 Bands, Ritual).
*   **Minor Action (1):** A character may only perform **one** Minor action per round. Typical Minor actions include: Shift 1 Range Band, Reload, Claim/Swap a Tactical Token, set up an Overwatch arc, or Stand from Prone.
*   **Free Action (Unlimited within reason):** Simple, narrative actions (Shout, Drop item).
*   **Reaction (1):** Interrupts that occur during the **Fast Phase** (e.g., Parry, Overwatch fire, Spend Tactical Token, Bonded Defence). Refreshes at the start of your turn.

### 3. Range-Band Zones & Movement

Combat occurs across four abstract Range Bands. These bands are **always measured pair-wise** between any two combatants, not from a central point on the battlefield.

| Band        | Scope       | Range Mod (to Attack) | Typical Actions          |
|-------------|-------------|-----------------------|--------------------------|
| **Engaged** | 0–2 m       | 0                     | Melee attacks, Tackle    |
| **Near**    | >2m–15 m    | –2                    | Short-range gunfire, Dash|
| **Far**     | >15m–50 m   | –4                    | Long-range attacks, Snipe|
| **Extreme** | >50 m       | –6                    | Very long-range, Artillery|

*   **Movement:**
    *   **Minor Action:** Shift 1 Range Band (e.g., Near to Engaged, Far to Near).
    *   **Major Action:** Shift 2 Range Bands (e.g., Far to Engaged) or enter Difficult Terrain within the current or an adjacent band.
    *   **Disengage (Minor Action):** If Engaged, make an Athletics check (vs. Difficulty 20, example) to safely shift 1 band away (e.g., Engaged to Near) without provoking a Breakaway. 
    *   **Breakaway:** If you move out of the Engaged band *without* using the Disengage action, any foes you were Engaged with may make an immediate free strike (Reaction) against you.

*   **Range Modifiers:** The Range Mod penalty applies to attack rolls made into a band or to a more distant band.

*   **Flat Modifiers Ladder:** Many situational modifiers use consistent steps of ±2, ±4, or ±6. 

---

### 4. Defences & The Aeonisk Defence Token

Aeonisk Tactical introduces a single **Defence Token** that represents your focused situational awareness.

* **Gaining & Refreshing**  
  • You start each combat round with **one (1) Defence Token**.  
  • It refreshes automatically at the beginning of the next round.

* **Allocating**  
  • During the **Declare Phase**, you **must** allocate your token to one visible foe. This allocation lasts for the entire round.
  • **If you forget to allocate,** you are considered to have no Defence Token active, and all attackers gain the benefit of Flanking (+2 to their attack rolls against you).

* **Benefit vs Allocated Foe**  
  • While the token is on that foe, they suffer **–2 to any roll that targets you directly** (attacks, aimed rituals, grapples).

* **Consequence vs Un-allocated Foes**  
  • Attacks from foes **not** holding your token count as **Flanking**: you take **–2 to your own Defence roll** (or, if you use static Defence, the attacker gains +2).

* **Heroic Burn (Evade Reaction)**  
  • **Once per combat,** you may choose to upgrade your Defence Token's effect to **–4**.
  • This decision can be made when you allocate the token or as a reaction to being attacked.
  • The token is considered **burned** and does **not** refresh for the remainder of the combat.

* **Interaction with Standard YAGS Defences**  
  • You still choose which incoming attacks to actively defend against per the core YAGS rules.  
  • The Defence Token’s modifier applies **before** you decide whether to split, full-defend, or take it on the chin.  
  • If you full-defend against your allocated foe, both the full-defence bonus **and** the token’s –2 (or –4 if Evade) apply—subject to the normal ±6 maximum.

* **One-Token-Per-PC Rule**  
  • A character can never hold more than one active Defence Token.  
  • If a rule, item, or power would grant an additional token, treat it as upgrading the existing one (still capped at –2 / –4 per above).

---

### 5. Tactical Tokens (Terrain & Positioning)

Tokens represent temporary advantages from terrain or position. 

*   **Lifecycle:**
    1.  **Claim (Minor Action):** Use a Minor action to claim a token representing a tactical advantage.
    2.  **Spend (Reaction):** Spend the token as a Reaction during the **Fast Phase** to gain its benefit.
    3.  **Discard:** The token is removed after use.
*   **Cap:** Only one (1) Tactical Token can be active per PC at a time.

| Token         | Claim Trigger (Narrative) | Spend Effect (Mechanical)                       |
|---------------|---------------------------|-------------------------------------------------|
| **Cover**     | Reach a solid object      | Grant +2 Soak against a single incoming attack.  |
| **High-Ground**| Climb to an elevation    | Gain +2 to an attack roll & ignore the Near band's range penalty for that attack.  |
| **Energy Hub**| Access a power conduit    | Gain +2 to one damage or effect roll. This bonus persists until nullified. |
| **Vent**      | Open a steam/gas vent     | Create a temporary area of obscurement.         |
| **Ley-Node**  | Enter a glowing sigil     | Gain +2 to a Dreamwork or Ritual roll.  |
| **Void Slick**| Step on an oily shimmer   | Target an enemy moving through it with an Agility save (DC 20) or they fall prone; may cause +1 Void splash to those in it.  |
| **Sprint Lane**| Find/clear a dash path  | Immediately make an extra Minor action band shift.  |

---

### 5a. Terrain & Obstructions

Movement through cluttered or hazardous environments requires an **Agility + Athletics** check before the movement is resolved. The DC is set by the GM based on the severity of the terrain.

| Terrain Type        | DC |
|---------------------|----|
| Light Clutter       | 10 |
| Unstable Crates     | 15 |
| Vacuum Breach       | 20 |

**Failure:** If the check fails, the character's declared movement (and any associated action, like a Charge) is lost, and they become **Prone**.

### 5b. Prone & Invalidated Actions

*   **Becoming Prone:** A character can be forced Prone by a failed terrain check or by an opponent's action.
*   **Invalidated Actions:** If an earlier-acting combatant forces you Prone **before** your Slow step, any declared action that requires standing (e.g., Charge, Sprint) automatically **fails**. You may not substitute this failed action; your Major action for the round is lost.
*   **Standing Up:** Standing from Prone costs a **Minor action** on your next turn.

---

### 6. Combat Modifiers

Situational modifiers apply as simple flat bonuses or penalties. 

| Situation                      | Modifier | Notes                                     |
|--------------------------------|----------|-------------------------------------------|
| Flanking an enemy in Engaged   | +2       | To attack rolls by both flanking characters.  |
| Attacking with High-Ground token | +2       | To that attack roll.  |
| Attacking Prone target (melee) | +2       | To melee attack rolls against them.  |
| Attacking Prone target (ranged)| –4       | To ranged attack rolls against them.  |
| Running while shooting         | –2       | To the shooter's attack roll.  |

---

### 7. New Tactical Actions

| Action      | Cost     | Requirement                      | Effect                                                                                                   |
|-------------|----------|----------------------------------|----------------------------------------------------------------------------------------------------------|
| **Suppress**| Major    | Weapon with Rate of Fire (RoF) ≥ 3 | On a successful hit: the target must choose to either Dive (immediately shift 1 band & lose Cover token if held) OR Hunker Down (suffer –4 to all their attack and defense rolls until their next turn).  |
| **Charge**  | Major    | Must start in Near or Far band   | Shift directly into the Engaged band with a chosen foe. Gain +2 to your first melee damage roll against that foe this turn, but you suffer –2 to your own defenses until your next turn.  |
| **Overwatch**| Minor to set up, uses Reaction to fire | Declare a 90° arc you are watching. | Make an immediate ranged attack (as a Reaction) against the first foe to enter or act significantly within that declared arc. This triggers **once** per round during the **Fast Phase**. |
| **Disengage**| Minor   | Must currently be Engaged        | Make an Athletics check (e.g., vs Difficulty 20) to shift 1 band away safely without provoking a Breakaway free strike.  |

---

### 8. Bond & Void Tactical Hooks

Special abilities leveraging core Aeonisk concepts. 

| Hook              | Cost          | Effect                                                                                                |
|-------------------|---------------|-------------------------------------------------------------------------------------------------------|
| **Bonded Defence**| Reaction      | When a Bonded ally is attacked, you can grant them +2 to their defense for that attack; however, you suffer –2 to your own defense against the next hit you take.  |
| **Bond Rally**    | Minor action  | Target a Bonded ally. Make an Empathy × Charm check (e.g., vs. Difficulty 20). If successful, you can pull 1 Stun from that ally onto yourself (you take the Stun, they heal it).  |
| **Void Surge**    | Free Action (declare before an attack roll) | Gain +4 to your damage roll for the current attack and it automatically causes Shock to the target on a hit. However, you immediately suffer 1 Stun from the spiritual backlash. **Unlimited usage allowed while Void ≤ 7; locked at Void ≥ 8.**  |

Bonded Defence – play snippet

A gunner on the catwalk opens fire at Kaelia.
Nyx uses their Reaction, projecting calm:
Kaelia rolls defence with +2 Bonded Defence.
—
Roll: Kaelia Defence d20 + Will×Agility + 2 = 14 + 2 = 16 vs Attack 18 → miss

A moment later, Nyx leans on their Bond…
Next time Nyx defends: they roll with –2 to that defence roll as the backlash penalty.

---

### 9. Character Sheet Integration

Minimal additions are needed:
*   **Phase Reminder:** A one-line reminder of the round structure: *Declare → Fast → Slow*.
*   **Stance:** A field to note character's current combat stance (normal / aggressive / defensive).
*   **Cover_Mod:** A temporary tracker for the +2 Soak granted by a Cover token.
*   No new persistent resource pools beyond core YAGS (Wounds, Soak, Void, etc.).

---

### 10. Roll Transparency Guidance

To maintain clarity and trust at the table, the GM should announce the raw d20 roll plus all modifiers aloud for each significant check. Alternatively, a log of rolls can be posted at the end of each character's turn.

### 11. Optional Zone Map Variant

For groups that prefer a more visual, board-game-like experience, an appendix can provide pre-fabricated maps with defined zones and their default Range Band relationships. For example, a cargo hold map could be divided into 5 zones: "Catwalk," "Central Crates," "Loading Bay," "Maintenance Tunnel," and "Control Room," with a table defining the band distance between each pair of zones.

---

### Appendix A: Printable Token Sheet

*(To be provided: SVG/PDF assets for the Tactical Tokens like Cover, High-Ground, Ley-Node, Void Slick, Sprint Lane, plus blank backs for custom terrain).*

### Appendix B: Quick-Ref Tables

*(To be compiled: Summary tables for Range Bands & Modifiers, Action Economy, Flat Modifiers, New Tactical Actions, Tactical Token benefits).*

---

## License

Distributed under the GPL v2 as described by Samuel Penn, the creator of Yet Another Game System (YAGS).

### Yet Another Game System

By Samuel Penn (sam@glendale.org.uk) and Aeonisk customization completed by Three Rivers AI Nexus.

Aeonisk YAGS Tactical Module is free content: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, version 2.

This content is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
