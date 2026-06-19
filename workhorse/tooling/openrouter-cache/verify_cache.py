#!/usr/bin/env python3
"""Prove that MiMo-V2.5 caching actually fires with the `xiaomi` provider pin.

Sends two identical large-prefix requests straight to OpenRouter (bypassing the
proxy and the agent CLI, to isolate the caching mechanics) and prints the
cached-token count for each. Call #1 writes the cache; call #2 should read it.

    export OPENROUTER_API_KEY=sk-or-v1-...   # or rely on .env next to this file
    python3 verify_cache.py

Exit 0 if call #2 shows cached tokens > 0 (caching confirmed), else exit 1.
"""
import json
import os
import sys
import urllib.error
import urllib.request

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = os.environ.get("VERIFY_MODEL", "xiaomi/mimo-v2.5")


def _load_dotenv() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, ".env")
    if not os.path.exists(path):
        return
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _big_prefix() -> str:
    # A stable prefix big enough to be worth caching (~3k tokens). Identical
    # bytes across both calls — that identity is what the cache keys on.
    para = (
        "You are a meticulous senior software engineer working inside an "
        "autonomous coding workflow. Follow the repository conventions exactly, "
        "keep changes minimal and well-scoped, and never invent files or APIs. "
    )
    return "SYSTEM CONTEXT (stable, cacheable):\n" + (para * 60)


def _call(key: str) -> dict:
    body = {
        "model": MODEL,
        # The guarantee: pin to the only provider that offers cache reads.
        "provider": {"order": ["xiaomi"], "allow_fallbacks": False},
        "usage": {"include": True},
        "max_tokens": 8,
        "messages": [
            {"role": "system", "content": _big_prefix()},
            {"role": "user", "content": "Reply with the single word OK."},
        ],
    }
    req = urllib.request.Request(
        OPENROUTER_URL,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def _cached_tokens(usage: dict) -> int:
    # OpenRouter reports cached prompt tokens here when the provider supports it.
    details = usage.get("prompt_tokens_details") or {}
    return int(details.get("cached_tokens") or 0)


def main() -> int:
    _load_dotenv()
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key or "REPLACE_ME" in key:
        print("ERROR: set OPENROUTER_API_KEY (env or .env)", file=sys.stderr)
        return 2

    print(f"model={MODEL}  provider=xiaomi (pinned, no fallback)\n")
    results = []
    for i in (1, 2):
        try:
            data = _call(key)
        except urllib.error.HTTPError as e:
            print(f"call #{i}: HTTP {e.code} — {e.read().decode()[:400]}", file=sys.stderr)
            return 1
        usage = data.get("usage", {})
        cached = _cached_tokens(usage)
        results.append(cached)
        print(
            f"call #{i}: prompt={usage.get('prompt_tokens')} "
            f"cached={cached} "
            f"cost=${usage.get('cost', 'n/a')} "
            f"provider={data.get('provider', '?')}"
        )

    print()
    if results[-1] > 0:
        print(f"✅ CACHING CONFIRMED — call #2 read {results[-1]} cached tokens.")
        return 0
    print(
        "❌ No cached tokens on call #2. Possible causes: prefix too short for "
        "this provider's min-cache threshold, caching disabled on the endpoint, "
        "or the request didn't route to `xiaomi`. Check the printed provider."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
