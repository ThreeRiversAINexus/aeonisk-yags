# Aeonisk Tactical Addendum Clarifications (v1.2)

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
1.  **Declare** (ascending INIT): State Major, Minor, Free actions, **Allocate Defence Token**.
2.  **Fast** actions (descending INIT)
3.  **Normal** actions (descending INIT)
4.  **Slow** actions (descending INIT)
5.  **Cleanup** (morale, effects, recovery)

**Actions per Turn**
| Type         | Count     | Notes                                                                |
|--------------|-----------|----------------------------------------------------------------------|
| **Major**    | 1         | Big moves: attacks, two-band shifts                                  |
| **Minor**    | 1         | Small but meaningful: one-band shift, Disengage, **draw/reload/item swap**, Guard, Claim a token  |
| **Free**     | Unlimited | Flavor narrations only: shout orders, drop an item (after you swapped it), quick emotive beats |
| **Reaction** | 1         | Interrupts: Parry, Overwatch, Token spend, Bonded Defence            |

**Damage & Recovery**
*   **Damage Roll:** Strength + Weapon Bonus + d20
*   **Soak:** Subtract from damage
*   **Wounds/Stun:** Every 5 damage = 1 Wound (serious) or 1 Stun (non-lethal) 
*   **Fatal:** > 5 Wounds → health check or die

---

### 1. Initiative, Tempo, and Round Structure

*   **Rolling Initiative:** At combat start, roll (Agility × 4) + d20. Natural 1 = Initiative 0 (Halves skill checks, all actions Slow for the round, unless Fatigue is taken).  Initiative score is generally kept for the encounter.
*   **Shock:** Reduces current Initiative. Can forfeit turn to re-roll Initiative (Agility x 4 + d20), halved if current Initiative is 0. 
*   **Round Order:**
    1.  **Declare Phase:** Characters (lowest to highest Initiative) declare their Major, Minor, and significant Free actions. They also allocate their Defence Token (see Section 4). Actions are committed.
    2.  **Action Resolution Phase:** Actions are resolved (highest to lowest Initiative) within Speed Bands:
        *   **Fast Actions** (e.g., Reactions like Parry, Token Spend) resolve first.
        *   **Normal Actions** (e.g., Minor Actions like 1-band shift, Item Swap, Guard) resolve next.
        *   **Slow Actions** (e.g., Major Actions like Attack, 2-band shift, Rituals) resolve last.
        *   *Note:* Higher Initiative always resolves first within its Speed Band.
    3.  **Cleanup Phase:** Resolve lingering effects, check Wounds/Stun, make morale checks.

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
*   **Minor Action (1):** Moderate actions (Shift 1 Band, Aim, **Draw/Reload/Item Swap**, Guard, Claim Tactical Token, Disengage). 
*   **Free Action (Unlimited within reason):** Simple, narrative actions (Shout, Drop item already swapped).
*   **Reaction (1):** Interrupts (Parry, Overwatch fire, Spend Tactical Token, Bonded Defence). Refreshes at start of your turn.

### 3. Range-Band Zones & Movement

Combat occurs across four abstract Range Bands, relative to a character's position. 

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

Aeonisk Tactical introduces a specific Defence Token mechanic.

*   **Gaining & Refreshing:** Each character has one (1) Defence Token available at the start of each combat round. It refreshes automatically.
*   **Allocating:** During the **Declare Phase**, you choose **one foe** to allocate your Defence Token against for the round. This allocation is fixed.
*   **Benefit vs Allocated Foe:** If the foe you allocated your token against attacks you this round, you gain a dedicated defensive bonus. *(Specific bonus [e.g., +X Soak, +Y to defence roll, attacker penalty] was noted as a design decision needed in the source material and is not defined in this version.)*
*   **Consequence vs Un-allocated Foe:** If you are attacked by a foe against whom you did *not* allocate your Defence Token, you do *not* receive the Defence Token's specific bonus against that attack. *(Any further specific consequence for being un-defended by this token [e.g., attacker bonus, potential for counter-attack] was noted as a design decision needed in the source material and is not defined in this version.)*
*   **Interaction with Standard YAGS Defence:** *(How this Aeonisk Defence Token interacts with core YAGS rules regarding declaring defences against multiple opponents was noted as a clarification needed in the source material and is not defined in this version.)*

---

### 5. Tactical Tokens (Terrain & Positioning)

Tokens represent temporary advantages from terrain or position. 

*   **Lifecycle:**
    1.  **Claim (Free/Minor Action):** Narrate securing the position (e.g., diving behind cover). Place token on your sheet.
    2.  **Spend (Reaction):** Flip token before a relevant roll/effect to gain its benefit.
    3.  **Discard:** Token is removed after use.
*   **Cap:** Only one (1) Tactical Token can be active per PC at a time.
*   **Synergy Cap:** Bonuses from Tactical Tokens (and other sources) cap at +2 per roll where Synergy applies.

| Token         | Claim Trigger (Narrative) | Spend Effect (Mechanical)                       |
|---------------|---------------------------|-------------------------------------------------|
| **Cover**     | Reach a solid object      | Grant +2 Soak against a single incoming attack.  |
| **High-Ground**| Climb to an elevation    | Gain +2 to an attack roll & ignore the Near band's range penalty for that attack.  |
| **Ley-Node**  | Enter a glowing sigil     | Gain +2 to a Dreamwork or Ritual roll.  |
| **Void Slick**| Step on an oily shimmer   | Target an enemy moving through it with an Agility save (DC 20) or they fall prone; may cause +1 Void splash to those in it.  |
| **Sprint Lane**| Find/clear a dash path  | Immediately make an extra Minor action band shift.  |

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
| **Overwatch**| Minor to set up, uses Reaction to fire | Declare a 90° arc you are watching. | Make an immediate ranged attack (as a Reaction) against the first foe to enter or act significantly within that declared arc.  |
| **Disengage**| Minor   | Must currently be Engaged        | Make an Athletics check (e.g., vs Difficulty 20) to shift 1 band away safely without provoking a Breakaway free strike.  |

---

### 8. Bond & Void Tactical Hooks

Special abilities leveraging core Aeonisk concepts. 

| Hook              | Cost          | Effect                                                                                                |
|-------------------|---------------|-------------------------------------------------------------------------------------------------------|
| **Bonded Defence**| Reaction      | When a Bonded ally is attacked, you can grant them +2 to their defense for that attack; however, you suffer –2 to your own defense against the next hit you take.  |
| **Bond Rally**    | Minor action  | Target a Bonded ally. Make an Empathy × Charm check (e.g., vs. Difficulty 20). If successful, you can pull 1 Stun from that ally onto yourself (you take the Stun, they heal it).  |
| **Void Surge**    | Free Action (declare before an attack roll) | Gain +4 to your damage roll for the current attack and it automatically causes Shock to the target on a hit. However, you immediately suffer 1 Stun from the spiritual backlash. **Unlimited usage allowed while Void ≤ 7; locked at Void ≥ 8.**  |

---

### 9. Character Sheet Integration

Minimal additions are needed:
*   **Stance:** A field to note character's current combat stance (normal / aggressive / defensive). *(Specific mechanical effects of stances were noted as a design decision needed in the source material.)*
*   **Cover_Mod:** A temporary tracker for the +2 Soak granted by a Cover token.
*   No new persistent resource pools beyond core YAGS (Wounds, Soak, Void, etc.).

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

Aeonisk YAGS Module is free content: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, version 2.

This content is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.