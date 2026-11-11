"""The todo web app on the standard library: the page, its script and the address of the API it talks to."""

from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).parent
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8"}


class WebServer:
    """The page on a loopback port. `api` is the address the page calls; `bug` plants a defect in the script."""

    def __init__(self, api: str, bug: str | None = None, port: int = 0) -> None:
        self.api = api
        self.bug = bug

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: object) -> None:
                return

            def do_GET(self) -> None:
                path = self.path.split("?", 1)[0]
                if path == "/config.js":
                    body = f"window.API_URL = {api!r}; window.BUG = {bug!r};".encode()
                    kind = TYPES[".js"]
                else:
                    name = "index.html" if path == "/" else path.lstrip("/")
                    found = HERE / name
                    if found.suffix not in TYPES or not found.is_file() or found.parent != HERE:
                        self.send_response(404)
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    body = found.read_bytes()
                    kind = TYPES[found.suffix]
                self.send_response(200)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self._server = ThreadingHTTPServer(("127.0.0.1", port), Handler)

    @property
    def port(self) -> int:
        return self._server.server_address[1]

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def serve_forever(self) -> None:
        self._server.serve_forever()


def main() -> None:
    server = WebServer(os.environ.get("API_URL", "http://127.0.0.1:8080"), os.environ.get("BUG") or None,
                       port=int(os.environ.get("PORT", "8081")))
    print("serving on", server.url, flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
