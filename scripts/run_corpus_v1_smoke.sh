#!/usr/bin/env bash
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR" || exit 1

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  cat <<'EOF'
Run the Corpus V1 golden smoke scenario once and write validation/audit reports.

Usage:
  scripts/run_corpus_v1_smoke.sh

Environment overrides:
  PYTHON           Python executable. Default: .venv/bin/python
  CONFIG           Scenario config. Default: healer/support corpus smoke config
  OUTPUT_BASE      Output root. Default: bulk_output/corpus_v1_bulk_cheap_smoke
  REPORT_DIR       Report directory. Default: OUTPUT_BASE/smoke_report_TIMESTAMP
  PROXY_URL        Batch proxy URL. Default: http://localhost:9090
  PRICING_FILE     Cost pricing JSON. Default: corpus_v1 bulk mini batch pricing
  SESSION_TIMEOUT  Per-session timeout in seconds. Default: 300

The script preflights PROXY_URL directly, then lets CONFIG drive batch_proxy
routing. It intentionally does not pass --proxy to bulk_session_runner.py
because that runner currently reinjects proxy settings as strategy=auto.
EOF
  exit 0
fi

PYTHON="${PYTHON:-.venv/bin/python}"
CONFIG="${CONFIG:-scripts/session_configs/corpus_v1_bulk_cheap/01_healer_support__medic_rescue_mission__gpt54mini_bulk.json}"
OUTPUT_BASE="${OUTPUT_BASE:-bulk_output/corpus_v1_bulk_cheap_smoke}"
PROXY_URL="${PROXY_URL:-http://localhost:9090}"
PRICING_FILE="${PRICING_FILE:-scripts/session_configs/corpus_v1_bulk_cheap/pricing_batch_gpt54mini.json}"
SESSION_TIMEOUT="${SESSION_TIMEOUT:-300}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
REPORT_DIR="${REPORT_DIR:-${OUTPUT_BASE}/smoke_report_${TIMESTAMP}}"

mkdir -p "$OUTPUT_BASE" "$REPORT_DIR"

run_report() {
  local name="$1"
  shift
  local outfile="${REPORT_DIR}/${name}.txt"
  {
    printf '$'
    printf ' %q' "$@"
    printf '\n\n'
  } > "$outfile"
  "$@" >> "$outfile" 2>&1
  local status=$?
  printf '%s\n' "$status" > "${REPORT_DIR}/${name}.exit"
  printf '%-28s exit=%s\n' "$name" "$status"
  return 0
}

run_json_report() {
  local name="$1"
  shift
  local outfile="${REPORT_DIR}/${name}.json"
  "$@" > "$outfile" 2> "${REPORT_DIR}/${name}.stderr"
  local status=$?
  printf '%s\n' "$status" > "${REPORT_DIR}/${name}.exit"
  printf '%-28s exit=%s\n' "$name" "$status"
  return 0
}

echo "Aeonisk Corpus V1 smoke"
echo "config:     $CONFIG"
echo "output:     $OUTPUT_BASE"
echo "report:     $REPORT_DIR"
echo "proxy:      $PROXY_URL"
echo "timeout:    ${SESSION_TIMEOUT}s"
echo

if [[ ! -x "$PYTHON" ]]; then
  echo "Python not executable: $PYTHON" >&2
  exit 2
fi

if [[ ! -f "$CONFIG" ]]; then
  echo "Config not found: $CONFIG" >&2
  exit 2
fi

if [[ ! -f "$PRICING_FILE" ]]; then
  echo "Pricing file not found: $PRICING_FILE" >&2
  exit 2
fi

"$PYTHON" - "$CONFIG" "$PROXY_URL" <<'PY'
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

config_path = Path(sys.argv[1])
proxy_url = sys.argv[2].rstrip("/")
config = json.loads(config_path.read_text())
errors = []

if config.get("max_turns") != 10:
    errors.append(f"max_turns is {config.get('max_turns')}, expected 10")

agents = config.get("agents") or {}
llms = []
if isinstance(agents.get("dm"), dict):
    llms.append(("dm", agents["dm"].get("llm") or {}))
for index, player in enumerate(agents.get("players") or [], start=1):
    llms.append((f"player_{index}", player.get("llm") or {}))
for key in ("enemies", "enemy_agents"):
    enemy = agents.get(key)
    if isinstance(enemy, dict) and "llm" in enemy:
        llms.append((key, enemy.get("llm") or {}))

for label, llm in llms:
    if llm.get("provider") != "batch_proxy":
        errors.append(f"{label} provider is {llm.get('provider')}, expected batch_proxy")
    if llm.get("proxy_strategy") != "batch":
        errors.append(f"{label} proxy_strategy is {llm.get('proxy_strategy')}, expected batch")
    if llm.get("proxy_url") != proxy_url:
        errors.append(f"{label} proxy_url is {llm.get('proxy_url')}, expected {proxy_url}")

if errors:
    for error in errors:
        print(f"config preflight failed: {error}", file=sys.stderr)
    raise SystemExit(2)

try:
    with urllib.request.urlopen(f"{proxy_url}/health", timeout=5) as response:
        print(f"proxy health: HTTP {response.status}")
except (urllib.error.URLError, TimeoutError) as exc:
    print(f"proxy health check failed for {proxy_url}/health: {exc}", file=sys.stderr)
    raise SystemExit(3)
PY
preflight_status=$?
if [[ "$preflight_status" -ne 0 ]]; then
  echo "Preflight failed; no paid run started." >&2
  exit "$preflight_status"
fi

run_report bulk_session \
  "$PYTHON" scripts/bulk_session_runner.py \
  --config "$CONFIG" \
  --runs 1 \
  --workers 1 \
  --output-dir "$OUTPUT_BASE" \
  --progress \
  --show-errors \
  --session-timeout "$SESSION_TIMEOUT"

run_report discover_complete \
  "$PYTHON" scripts/yags_mine.py discover "$OUTPUT_BASE" \
  --complete-only \
  --min-rounds 10 \
  --limit 20

run_report validate_text \
  "$PYTHON" scripts/yags_mine.py validate "$OUTPUT_BASE" \
  --recursive

run_report validate_strict \
  "$PYTHON" scripts/yags_mine.py validate "$OUTPUT_BASE" \
  --recursive \
  --strict

run_json_report validate_json \
  "$PYTHON" scripts/yags_mine.py validate "$OUTPUT_BASE" \
  --recursive \
  --format json

run_report analyze_summary \
  "$PYTHON" scripts/yags_mine.py analyze "$OUTPUT_BASE" \
  --mode summary \
  --recursive \
  --limit 20

run_report analyze_errors \
  "$PYTHON" scripts/yags_mine.py analyze "$OUTPUT_BASE" \
  --mode errors \
  --recursive \
  --limit 20

run_report analyze_void \
  "$PYTHON" scripts/yags_mine.py analyze "$OUTPUT_BASE" \
  --mode void \
  --recursive \
  --limit 20

run_report analyze_clocks \
  "$PYTHON" scripts/yags_mine.py analyze "$OUTPUT_BASE" \
  --mode clocks \
  --recursive \
  --limit 20

run_report balance_text \
  "$PYTHON" scripts/yags_mine.py balance "$OUTPUT_BASE" \
  --recursive \
  --verbose

run_json_report balance_json \
  "$PYTHON" scripts/yags_mine.py balance "$OUTPUT_BASE" \
  --recursive \
  --format json

run_report cost_text \
  "$PYTHON" scripts/yags_mine.py cost "$OUTPUT_BASE" \
  --recursive \
  --pricing-file "$PRICING_FILE"

run_json_report cost_json \
  "$PYTHON" scripts/yags_mine.py cost "$OUTPUT_BASE" \
  --recursive \
  --pricing-file "$PRICING_FILE" \
  --format json

"$PYTHON" - "$REPORT_DIR" "$OUTPUT_BASE" "$CONFIG" <<'PY'
import json
import sys
from pathlib import Path

report_dir = Path(sys.argv[1])
output_base = Path(sys.argv[2])
config = sys.argv[3]

def read_exit(name):
    path = report_dir / f"{name}.exit"
    return path.read_text().strip() if path.exists() else "missing"

def load_json(name):
    path = report_dir / name
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None

validation = load_json("validate_json.json") or {}
cost = load_json("cost_json.json") or {}
balance = load_json("balance_json.json")
session_files = sorted(output_base.rglob("session_*.jsonl"))
validation_summary = validation.get("summary") or {}

lines = [
    "# Corpus V1 Smoke Audit",
    "",
    f"- Config: `{config}`",
    f"- Output base: `{output_base}`",
    f"- Report dir: `{report_dir}`",
    f"- Session files found: {len(session_files)}",
    "",
    "## Command Status",
    "",
]

for name in [
    "bulk_session",
    "discover_complete",
    "validate_text",
    "validate_strict",
    "validate_json",
    "analyze_summary",
    "analyze_errors",
    "analyze_void",
    "analyze_clocks",
    "balance_text",
    "balance_json",
    "cost_text",
    "cost_json",
]:
    lines.append(f"- `{name}`: exit {read_exit(name)}")

lines.extend(["", "## Validation", ""])
if validation:
    lines.append(f"- Sessions: {validation_summary.get('total_sessions', 'unknown')}")
    lines.append(f"- Passed: {validation_summary.get('passed_sessions', 'unknown')}")
    lines.append(f"- Failed: {validation_summary.get('failed_sessions', 'unknown')}")
    lines.append(f"- Total errors: {validation_summary.get('total_errors', 'unknown')}")
    lines.append(f"- Total warnings: {validation_summary.get('total_warnings', 'unknown')}")
else:
    lines.append("- Validation JSON was not available or was not parseable.")

lines.extend(["", "## Cost", ""])
if cost:
    lines.append(f"- Session files: {cost.get('session_files', 'unknown')}")
    lines.append(f"- Calls: {cost.get('calls', 'unknown')}")
    lines.append(f"- Input tokens: {cost.get('input_tokens', 'unknown')}")
    lines.append(f"- Output tokens: {cost.get('output_tokens', 'unknown')}")
    lines.append(f"- Estimated batch cost: ${float(cost.get('cost_usd') or 0):.6f}")
    buckets = cost.get("buckets") or []
    for bucket in buckets[:12]:
        lines.append(
            "- Bucket: "
            f"{bucket.get('agent_type')} {bucket.get('provider')}/{bucket.get('model')} "
            f"calls={bucket.get('calls')} "
            f"cost=${float(bucket.get('cost_usd') or 0):.6f}"
        )
else:
    lines.append("- Cost JSON was not available or was not parseable.")

lines.extend(["", "## Bug Triage Checklist", ""])
lines.append("- Check `validate_strict.txt` first. Any warning there blocks Gold data use.")
lines.append("- Check `analyze_errors.txt` for runtime exceptions, fallbacks, schema retries, and impossible state transitions.")
lines.append("- Check `analyze_clocks.txt` for clocks that stall, regress incorrectly, or finish without narrative consequence.")
lines.append("- Check `analyze_void.txt` for runaway void escalation or missing void consequences.")
lines.append("- Check `balance_text.txt` for skill, weapon, enemy, economy, and targeting skew.")
lines.append("- Check `cost_text.txt` for cost per clean session before scaling.")
lines.append("- Confirm proxy logs show `routed_via: batch` or equivalent batch submission IDs.")

lines.extend(["", "## Session Files", ""])
for path in session_files[:50]:
    lines.append(f"- `{path}`")

if balance is None:
    lines.extend(["", "## Balance JSON", "", "- Balance JSON was not available or was not parseable."])

(report_dir / "SMOKE_AUDIT.md").write_text("\n".join(lines) + "\n")
print(report_dir / "SMOKE_AUDIT.md")
PY

echo
echo "Smoke audit written to: ${REPORT_DIR}/SMOKE_AUDIT.md"
echo "Review strict validation, error analysis, cost, and proxy logs before running more scenarios."
