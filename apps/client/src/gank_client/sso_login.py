"""Desktop OAuth handoff: EVE's SSO redirect URI is fixed to our api's
/auth/eve/callback (must match what's registered at
developers.eveonline.com), so the client can't receive the code directly.
Instead: open the system browser at api's /login with a `return_to`
pointing at a one-shot local HTTP server, and let the api redirect the
browser back here with our own opaque api_token once the EVE side is done.
"""

from __future__ import annotations

import threading
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

from gank_client.config import API_BASE


@dataclass
class LoginResult:
    api_token: str
    character_id: int
    character_name: str


def start_login(on_result: callable) -> None:
    """Spins up a one-shot loopback server on a background thread, opens
    the system browser at api's login endpoint, and calls on_result(...)
    with a LoginResult (or None on failure) once the browser redirects back.
    """
    result_holder: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:  # silence default stderr logging
            pass

        def do_GET(self) -> None:
            query = parse_qs(urlparse(self.path).query)
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body>Logged in. You can close this window.</body></html>")

            if "api_token" in query:
                result_holder["result"] = LoginResult(
                    api_token=query["api_token"][0],
                    character_id=int(query["character_id"][0]),
                    character_name=query["character_name"][0],
                )
            threading.Thread(target=server.shutdown, daemon=True).start()

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]

    def serve() -> None:
        server.serve_forever()
        on_result(result_holder.get("result"))

    threading.Thread(target=serve, daemon=True).start()

    return_to = f"http://127.0.0.1:{port}/callback"
    webbrowser.open(f"{API_BASE}/auth/eve/login?{urlencode({'return_to': return_to})}")
