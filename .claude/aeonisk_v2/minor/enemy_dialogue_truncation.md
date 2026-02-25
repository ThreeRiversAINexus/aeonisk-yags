# Enemy Dialogue Truncated in DM Narration

## Bug
When enemy agents choose `MAJOR_ACTION: Dialogue` and provide detailed `DIALOGUE_CONTENT`, the DM narration reduces their speech to a single generic line:
```
"ACG Security Patrol #1 attempts to communicate."
```

This completely erases the nuanced dialogue the enemy AI generated — corporate diplomacy, legal threats, individual targeting of PCs by name, coordinated stalling tactics, etc.

## Evidence
Session `f02f7c8f-19ab-4507-8ce5-4553f173b876`, Rounds 15-17:
- ACG Security Patrol #1 generated 2 detailed dialogue actions (addressing each PC by name, invoking salvage jurisdiction, offering medical quarantine, threatening Hammerhead arrival)
- ACG Security Patrol #2 generated 2 detailed dialogue actions (quarantine violations, Nexus-ACG joint custody agreements, escalating pressure)
- DM narration for ALL four actions: `"[name] attempts to communicate."`

## Impact
- PCs never receive enemy dialogue content in their context
- Multi-round enemy negotiation tactics are invisible to the narrative
- The enemy AI's best work (coordinated stalling, exploiting faction tensions) is thrown away
- Breaks narrative cohesion — enemies appear as mute threats rather than intelligent actors

## Root Cause (suspected)
The DM synthesis prompt likely receives enemy actions in a summary format that strips `DIALOGUE_CONTENT`. Or the DM narration template for enemy "dialogue" actions uses a generic fallback instead of injecting the actual speech.

## Fix
Ensure `DIALOGUE_CONTENT` from enemy agent dialogue actions is passed through to the DM narration context and rendered in the round synthesis narration, similar to how NPC dialogue is handled (the Transit Hub Dock Supervisor's dialogue DID appear in full).
