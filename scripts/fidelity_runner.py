#!/usr/bin/env python3
"""Live runner for rules-fidelity sweeps.

Three modes:
    run     Parallel direct calls (OpenAI-compatible or Anthropic).
            Use for providers without a batch API (e.g. DeepInfra) or smokes.
    submit  Upload a batch request file (from: yags_mine.py fidelity-eval
            batchfile) to the OpenAI Batch API or Anthropic Message Batches.
    poll    Check a submitted batch; when finished, download results.

Outputs are plain responses JSONL ({"item_id", "response"}) ready for
`yags_mine.py fidelity-eval score` (direct runs) — batch outputs are saved
in the provider dialect and scored with --responses-format.

Examples:
    fidelity_runner.py run --prompts prompts.jsonl --provider deepinfra \
        --model zai-org/GLM-5.1 --output glm.jsonl --workers 8 --limit 5
    fidelity_runner.py submit --batchfile openai_batch.jsonl --provider openai
    fidelity_runner.py poll --provider openai --batch-id batch_abc \
        --output gpt.jsonl
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

scripts_dir = Path(__file__).parent
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))

OPENAI_BASE = "https://api.openai.com/v1"
DEEPINFRA_BASE = "https://api.deepinfra.com/v1/openai"
GEMINI_OPENAI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"
ANTHROPIC_BASE = "https://api.anthropic.com/v1"

PROVIDER_KEYS = {
    "openai": "OPENAI_API_KEY",
    "deepinfra": "DEEPINFRA_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}

PROVIDER_BASES = {
    "openai": OPENAI_BASE,
    "deepinfra": DEEPINFRA_BASE,
    "gemini": GEMINI_OPENAI_BASE,
}


def build_chat_body(prompt: dict, model: str, max_tokens: int,
                    reasoning_effort: str = None) -> dict:
    """OpenAI-compatible chat.completions request body."""
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt["system"]},
            {"role": "user", "content": prompt["user"]},
        ],
        "max_completion_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    if reasoning_effort:
        body["reasoning_effort"] = reasoning_effort
    return body


def build_anthropic_body(prompt: dict, model: str, max_tokens: int) -> dict:
    return {
        "model": model,
        "max_tokens": max_tokens,
        "system": prompt["system"],
        "messages": [{"role": "user", "content": prompt["user"]}],
    }


def extract_chat_content(payload: dict) -> str:
    try:
        return payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        # e.g. thinking models that exhaust max_tokens before emitting text
        return None


def extract_anthropic_content(payload: dict) -> str:
    return "".join(block.get("text", "") for block in payload.get("content", [])
                   if block.get("type") == "text")


def _api_key(provider: str) -> str:
    key = os.environ.get(PROVIDER_KEYS[provider], "")
    if not key:
        print(f"Error: {PROVIDER_KEYS[provider]} not set", file=sys.stderr)
        sys.exit(1)
    return key


def _read_jsonl(path) -> list:
    records = []
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _call_one(prompt: dict, args, key: str) -> dict:
    for attempt in range(4):
        try:
            if args.provider == "anthropic":
                response = requests.post(
                    f"{ANTHROPIC_BASE}/messages",
                    headers={"x-api-key": key,
                             "anthropic-version": "2023-06-01"},
                    json=build_anthropic_body(prompt, args.model,
                                              args.max_tokens),
                    timeout=120,
                )
                if response.status_code == 200:
                    payload = response.json()
                    usage = payload.get("usage", {})
                    return {"item_id": prompt["item_id"],
                            "response": extract_anthropic_content(payload),
                            "usage": usage}
            else:
                base = getattr(args, "base_url", None) or PROVIDER_BASES[args.provider]
                response = requests.post(
                    f"{base}/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json=build_chat_body(prompt, args.model, args.max_tokens,
                                         args.reasoning_effort),
                    timeout=120,
                )
                if response.status_code == 200:
                    payload = response.json()
                    return {"item_id": prompt["item_id"],
                            "response": extract_chat_content(payload),
                            "usage": payload.get("usage", {})}
            if response.status_code in (429, 500, 502, 503, 529):
                time.sleep(2 ** attempt)
                continue
            return {"item_id": prompt["item_id"], "response": None,
                    "error": f"HTTP {response.status_code}: {response.text[:200]}"}
        except requests.RequestException as exc:
            if attempt == 3:
                return {"item_id": prompt["item_id"], "response": None,
                        "error": str(exc)[:200]}
            time.sleep(2 ** attempt)
    return {"item_id": prompt["item_id"], "response": None,
            "error": "retries exhausted"}


def cmd_run(args) -> int:
    key = _api_key(args.provider)
    prompts = _read_jsonl(args.prompts)
    if args.limit:
        prompts = prompts[:args.limit]

    results = []
    errors = 0
    total_in = total_out = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_call_one, p, args, key): p for p in prompts}
        for index, future in enumerate(as_completed(futures), 1):
            record = future.result()
            results.append(record)
            usage = record.pop("usage", {}) or {}
            total_in += usage.get("input_tokens") or usage.get("prompt_tokens") or 0
            total_out += (usage.get("output_tokens")
                          or usage.get("completion_tokens") or 0)
            if record.get("error"):
                errors += 1
            if index % 50 == 0 or index == len(prompts):
                print(f"  {index}/{len(prompts)} done ({errors} errors)",
                      file=sys.stderr)

    with open(args.output, "w") as handle:
        for record in results:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"Wrote {len(results)} responses to {args.output} "
          f"({errors} errors; tokens in={total_in} out={total_out})",
          file=sys.stderr)
    return 0 if errors == 0 else 1


def cmd_submit(args) -> int:
    key = _api_key(args.provider)
    if args.provider == "openai":
        with open(args.batchfile, "rb") as handle:
            upload = requests.post(
                f"{OPENAI_BASE}/files",
                headers={"Authorization": f"Bearer {key}"},
                files={"file": (Path(args.batchfile).name, handle)},
                data={"purpose": "batch"}, timeout=300,
            )
        upload.raise_for_status()
        file_id = upload.json()["id"]
        created = requests.post(
            f"{OPENAI_BASE}/batches",
            headers={"Authorization": f"Bearer {key}"},
            json={"input_file_id": file_id,
                  "endpoint": "/v1/chat/completions",
                  "completion_window": "24h"},
            timeout=60,
        )
        created.raise_for_status()
        print(created.json()["id"])
        return 0
    if args.provider == "anthropic":
        batch_requests = _read_jsonl(args.batchfile)
        created = requests.post(
            f"{ANTHROPIC_BASE}/messages/batches",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
            json={"requests": batch_requests}, timeout=300,
        )
        created.raise_for_status()
        print(created.json()["id"])
        return 0
    print(f"Error: no batch API for provider '{args.provider}'",
          file=sys.stderr)
    return 1


def cmd_poll(args) -> int:
    key = _api_key(args.provider)
    if args.provider == "openai":
        status = requests.get(
            f"{OPENAI_BASE}/batches/{args.batch_id}",
            headers={"Authorization": f"Bearer {key}"}, timeout=60,
        )
        status.raise_for_status()
        payload = status.json()
        print(f"status={payload['status']} counts={payload.get('request_counts')}",
              file=sys.stderr)
        if payload["status"] != "completed":
            return 2
        output = requests.get(
            f"{OPENAI_BASE}/files/{payload['output_file_id']}/content",
            headers={"Authorization": f"Bearer {key}"}, timeout=300,
        )
        output.raise_for_status()
        Path(args.output).write_text(output.text)
        print(f"Wrote batch output to {args.output}", file=sys.stderr)
        return 0
    if args.provider == "anthropic":
        status = requests.get(
            f"{ANTHROPIC_BASE}/messages/batches/{args.batch_id}",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
            timeout=60,
        )
        status.raise_for_status()
        payload = status.json()
        print(f"status={payload['processing_status']} "
              f"counts={payload.get('request_counts')}", file=sys.stderr)
        if payload["processing_status"] != "ended":
            return 2
        results = requests.get(
            payload["results_url"],
            headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
            timeout=300,
        )
        results.raise_for_status()
        Path(args.output).write_text(results.text)
        print(f"Wrote batch output to {args.output}", file=sys.stderr)
        return 0
    print(f"Error: no batch API for provider '{args.provider}'",
          file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Live runner for rules-fidelity sweeps",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = parser.add_subparsers(dest="mode")

    run_parser = sub.add_parser("run", help="Parallel direct calls")
    run_parser.add_argument("--prompts", required=True)
    run_parser.add_argument("--provider", required=True,
                            choices=["openai", "deepinfra", "gemini", "anthropic"])
    run_parser.add_argument("--base-url",
                            help="Override the OpenAI-compatible base URL")
    run_parser.add_argument("--model", required=True)
    run_parser.add_argument("--output", required=True)
    run_parser.add_argument("--workers", type=int, default=8)
    run_parser.add_argument("--max-tokens", type=int, default=300)
    run_parser.add_argument("--limit", type=int)
    run_parser.add_argument("--reasoning-effort",
                            choices=["none", "minimal", "low", "medium", "high"])

    submit_parser = sub.add_parser("submit", help="Submit a batch file")
    submit_parser.add_argument("--batchfile", required=True)
    submit_parser.add_argument("--provider", required=True,
                               choices=["openai", "anthropic"])

    poll_parser = sub.add_parser("poll", help="Poll a batch, fetch results")
    poll_parser.add_argument("--provider", required=True,
                             choices=["openai", "anthropic"])
    poll_parser.add_argument("--batch-id", required=True)
    poll_parser.add_argument("--output", required=True)

    args = parser.parse_args()
    if args.mode == "run":
        return cmd_run(args)
    if args.mode == "submit":
        return cmd_submit(args)
    if args.mode == "poll":
        return cmd_poll(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
