#!/usr/bin/env python3
"""Diagnostic OpenAI-compatible proxy: records every request and pins OpenRouter
to the `xiaomi` provider, then forwards to OpenRouter.

Two jobs:
  1. Inject `provider:{order:[xiaomi],allow_fallbacks:false}` + usage accounting
     (so caching fires) — same guarantee as the LiteLLM proxy, dependency-free.
  2. Save each inbound request body to CAPTURE_DIR/req_<n>.json so we can check
     whether the *client* (e.g. Copilot CLI) keeps an append-only prefix across
     agentic turns — the client-side half of "does caching actually help".

    OPENROUTER_API_KEY=... python3 pin_proxy.py serve [--port 4100] [--dir runs/cap]
    python3 pin_proxy.py analyze runs/cap     # prefix-stability + cache report
"""
import json
import os
import sys
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_RESPONSES = "https://openrouter.ai/api/v1/responses"
OPENROUTER_MODELS = "https://openrouter.ai/api/v1/models"
CAPTURE_DIR = os.environ.get("CAPTURE_DIR", "runs/capture")
_seq = {"n": 0}


def _load_dotenv() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, ".env")
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def _key() -> str:
    k = os.environ.get("OPENROUTER_API_KEY", "")
    if not k or "REPLACE_ME" in k:
        sys.exit("ERROR: set OPENROUTER_API_KEY (env or .env)")
    return k


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quieter
        pass

    def do_GET(self):
        # Some CLIs probe /models on startup. Pass OpenRouter's list through.
        if self.path.rstrip("/").endswith("/models"):
            try:
                req = urllib.request.Request(
                    OPENROUTER_MODELS, headers={"Authorization": f"Bearer {_key()}"}
                )
                data = urllib.request.urlopen(req, timeout=30).read()
            except Exception as e:  # noqa: BLE001
                data = json.dumps({"data": [], "error": str(e)}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        try:
            payload = json.loads(body)
        except Exception:  # noqa: BLE001
            payload = {}

        # ── Record the inbound request for prefix-stability analysis ──────────
        _seq["n"] += 1
        os.makedirs(CAPTURE_DIR, exist_ok=True)
        with open(os.path.join(CAPTURE_DIR, f"req_{_seq['n']:03d}.json"), "w") as fh:
            json.dump(payload, fh, indent=2)

        # ── The guarantee: pin provider + ask for usage accounting ────────────
        payload["provider"] = {"order": ["xiaomi"], "allow_fallbacks": False}
        payload["usage"] = {"include": True}
        streaming = bool(payload.get("stream"))
        if streaming:
            payload.setdefault("stream_options", {})["include_usage"] = True

        # Codex 0.128+ uses the Responses API (POST .../responses, field `input`);
        # claude/copilot use Chat Completions (`messages`). Route to the matching
        # OpenRouter endpoint — both honor the provider pin and report cache.
        target = OPENROUTER_RESPONSES if self.path.rstrip("/").endswith("/responses") else OPENROUTER
        up = urllib.request.Request(
            target,
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {_key()}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            resp = urllib.request.urlopen(up, timeout=300)
        except urllib.error.HTTPError as e:
            err = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(err)
            print(f"[req {_seq['n']}] upstream {e.code}: {err[:200]!r}", file=sys.stderr)
            return

        self.send_response(200)
        self.send_header(
            "Content-Type", "text/event-stream" if streaming else "application/json"
        )
        self.end_headers()

        captured = bytearray()
        while True:
            chunk = resp.read(2048)
            if not chunk:
                break
            captured += chunk
            try:
                self.wfile.write(chunk)
                self.wfile.flush()
            except BrokenPipeError:
                break

        self._log_usage(bytes(captured), streaming)

    def _log_usage(self, raw: bytes, streaming: bool) -> None:
        usage = None
        try:
            if streaming:
                for line in raw.decode(errors="replace").splitlines():
                    if line.startswith("data:") and '"usage"' in line:
                        obj = json.loads(line[5:].strip())
                        # Chat puts usage at top level; the Responses API nests it
                        # under the final response.completed event's `response`.
                        usage = obj.get("usage") or (obj.get("response") or {}).get("usage") or usage
            else:
                doc = json.loads(raw.decode())
                usage = doc.get("usage") or (doc.get("response") or {}).get("usage")
        except Exception:  # noqa: BLE001
            pass
        if usage:
            # Chat: prompt_tokens(+_details). Responses: input_tokens(+_details).
            details = usage.get("prompt_tokens_details") or usage.get("input_tokens_details") or {}
            cached = details.get("cached_tokens", 0)
            prompt = usage.get("prompt_tokens", usage.get("input_tokens"))
            line = (
                f"[req {_seq['n']}] prompt={prompt} "
                f"cached={cached} cost=${usage.get('cost', 'n/a')}"
            )
            print(line, file=sys.stderr)
            with open(os.path.join(CAPTURE_DIR, "usage.log"), "a") as fh:
                fh.write(line + "\n")


def _messages(req: dict) -> list:
    # Chat Completions uses `messages`; the Responses API (codex) uses `input`.
    msgs = req.get("messages")
    if msgs is not None:
        return msgs
    inp = req.get("input")
    return inp if isinstance(inp, list) else ([] if inp is None else [inp])


def analyze(cap_dir: str) -> int:
    files = sorted(
        f for f in os.listdir(cap_dir) if f.startswith("req_") and f.endswith(".json")
    )
    if len(files) < 2:
        print(f"Only {len(files)} request(s) captured — need >= 2 turns to judge "
              "prefix stability. Drive a task that makes the model call a tool.")
        return 1

    reqs = [json.load(open(os.path.join(cap_dir, f))) for f in files]
    print(f"Captured {len(reqs)} requests from {cap_dir}\n")
    stable = True
    for i in range(1, len(reqs)):
        prev, cur = _messages(reqs[i - 1]), _messages(reqs[i])
        # Append-only ⇔ prev is an exact element-wise prefix of cur.
        is_prefix = len(cur) >= len(prev) and all(
            json.dumps(cur[j], sort_keys=True) == json.dumps(prev[j], sort_keys=True)
            for j in range(len(prev))
        )
        added = len(cur) - len(prev)
        if is_prefix:
            print(f"turn {i}→{i+1}: ✅ append-only  (+{added} msgs, prefix of {len(prev)} intact)")
        else:
            stable = False
            # find first divergence
            d = next(
                (j for j in range(min(len(prev), len(cur)))
                 if json.dumps(cur[j], sort_keys=True) != json.dumps(prev[j], sort_keys=True)),
                min(len(prev), len(cur)),
            )
            print(f"turn {i}→{i+1}: ❌ PREFIX BROKEN at message index {d} "
                  f"(prev {len(prev)} msgs, cur {len(cur)} msgs) — cache cold-misses here")

    print()
    if os.path.exists(os.path.join(cap_dir, "usage.log")):
        print("Upstream usage:")
        print(open(os.path.join(cap_dir, "usage.log")).read().rstrip())
    print()
    if stable:
        print("✅ CLIENT-SIDE STABLE — prefix is append-only across all turns; "
              "the xiaomi cache stays warm and bills cached reads on later turns.")
        return 0
    print("❌ CLIENT-SIDE UNSTABLE — the client rewrites its prefix between turns, "
          "so caching cold-misses despite the provider pin. Prefer the claude CLI.")
    return 1


def main() -> int:
    _load_dotenv()
    if len(sys.argv) >= 2 and sys.argv[1] == "analyze":
        return analyze(sys.argv[2] if len(sys.argv) > 2 else CAPTURE_DIR)
    # serve
    port = 4000
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    if "--dir" in sys.argv:
        globals()["CAPTURE_DIR"] = sys.argv[sys.argv.index("--dir") + 1]
    _key()  # fail fast if missing
    os.makedirs(CAPTURE_DIR, exist_ok=True)
    print(f"pin_proxy on :{port} → OpenRouter (xiaomi pinned); capturing to {CAPTURE_DIR}",
          file=sys.stderr)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
