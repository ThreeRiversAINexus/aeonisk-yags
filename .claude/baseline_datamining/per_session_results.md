# Per-Session Results

## Successful Sessions (20/25)

| Run | DM Model | Rounds | Kael HP | Kael Status | Sable HP | Sable Status | Enemies Spawned | Enemies Defeated | NPC Behaviors | Tokens | Duration |
|-----|----------|--------|---------|-------------|----------|-------------|----------------|-----------------|---------------|--------|----------|
| 0001 | GPT-5.2 | 4 | 0/27 | unconscious | 0/27 | dead | 5 | 3 | hide:3 | 412,350 | 499s |
| 0006 | GPT-5.2 | 6 | 0/27 | unconscious | 0/27 | unconscious | 8 | 2 | hide:2 | 624,910 | 629s |
| 0011 | GPT-5.2 | 10 | 24/27 | alive | 0/27 | unconscious | 13 | 4 | hide:2 | 1,107,952 | 1,116s |
| 0016 | GPT-5.2 | 10 | 17/27 | alive | 0/27 | unconscious | 14 | 3 | dialogue:5, hide:2 | 1,025,273 | 1,027s |
| 0021 | GPT-5.2 | 5 | 0/27 | dead | 0/27 | unconscious | 7 | 2 | hide:1 | 515,298 | 490s |
| 0002 | Grok 4 | 7 | 0/27 | unconscious | 0/27 | unconscious | 12 | 8 | flee:4, hide:1 | 687,195 | 3,553s |
| 0007 | Grok 4 | 7 | 0/27 | unconscious | 0/27 | unconscious | 13 | 0 | flee:2, hide:2, plead:1 | 705,330 | 3,529s |
| 0012 | Grok 4 | 10 | 2/27 | alive | 23/27 | alive | 19 | 1 | flee:3, plead:1, hide:1 | 1,206,048 | 3,534s |
| 0017 | Grok 4 | 10 | 27/27 | alive | 27/27 | alive | 9 | 4 | attack:7, heal:6, plead:4, dialogue:4, flee:2 | 1,210,813 | 4,891s |
| 0022 | Grok 4 | 4 | 0/27 | unconscious | 0/27 | unconscious | 7 | 1 | flee:2 | 448,579 | 1,845s |
| 0003 | Gemini 2.5 Pro | 4 | 0/27 | unconscious | 0/27 | dead | 7 | 0 | hide:2 | 408,588 | 1,324s |
| 0008 | Gemini 2.5 Pro | 3 | 0/27 | unconscious | 0/27 | unconscious | 11 | 0 | hide:1, flee:1, plead:1 | 302,473 | 926s |
| 0013 | Gemini 2.5 Pro | 6 | 0/27 | unconscious | 0/27 | dead | 9 | 0 | dialogue:3, hide:1, heal:1 | 488,574 | 1,455s |
| 0018 | Gemini 2.5 Pro | 6 | 0/27 | dead | 0/27 | unconscious | 8 | 0 | dialogue:5, hide:2 | 492,465 | 1,456s |
| 0023 | Gemini 2.5 Pro | 6 | 0/27 | unconscious | 0/27 | dead | 12 | 0 | dialogue:3, hide:2, plead:1, comply:1 | 538,626 | 1,399s |
| 0005 | DeepSeek V3.2 | 10 | 0/27 | unconscious | 0/27 | dead | 13 | 2 | hide:6, dialogue:4 | 1,029,138 | 3,421s |
| 0010 | DeepSeek V3.2 | 9 | 0/27 | unconscious | 0/27 | unconscious | 12 | 3 | plead:7, hide:3, dialogue:3 | 766,364 | 2,282s |
| 0015 | DeepSeek V3.2 | 10 | 5/27 | alive | 27/27 | alive | 11 | 3 | hide:2, dialogue:2, plead:1 | 1,147,944 | 4,375s |
| 0020 | DeepSeek V3.2 | 9 | 0/27 | dead | 0/27 | unconscious | 9 | 0 | plead:9, dialogue:7, hide:2 | 910,883 | 5,590s |
| 0025 | DeepSeek V3.2 | 5 | 0/27 | unconscious | 0/27 | unconscious | 5 | 1 | hide:4, dialogue:2 | 428,786 | 2,800s |

## Failed Sessions (5/25) — All Anthropic Claude Opus 4.6

| Run | Rounds Before Fail | Error | Tokens Used | Duration |
|-----|-------------------|-------|-------------|----------|
| 0004 | 2 | `ActionResolution` parse fail: empty response (3 retries) | 151,709 | 7,643s |
| 0009 | 1 | Same error | 38,250 | 5,430s |
| 0014 | 1 | Same error | 37,592 | 2,038s |
| 0019 | 1 | Same error | 37,572 | 1,014s |
| 0024 | 1 | Same error | 38,060 | 432s |

See `claude_failure_analysis.md` for root cause investigation.

## Column Notes

- **Enemies Defeated** counts all `enemy_defeat` events, which include: killed, fled, retreated, subdued, departed, despawned. This conflates combat kills with narrative departures. Use `defeat_reason` field in JSONL data to distinguish.

## Status Definitions

- **alive/active**: HP > 0, still acting
- **unconscious**: HP = 0, not dead (can be stabilized)
- **dead**: Beyond recovery (multiple wounds, confirmed kill)

Note: "pc_defeated" flag was false for all sessions — this is an unrelated system flag, not the combat outcome. Use HP + status to determine actual combat results.
