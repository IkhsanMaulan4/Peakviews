"""Token-protected local HTTP server for the PeakView web UI (stdlib only)."""
import hmac
import json
import secrets
import socket
import threading
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from report import NoDataError
from web_api import (
    WebContext, apply_segment, build_state, build_summary, build_timeline,
)

MAX_BODY = 1024
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
# Explicit table: Windows' registry-backed mimetypes can mislabel .js as text/plain.
MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}
CSP = "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'"


def lan_ip() -> str:
    """Best-effort LAN address of this machine (no packet is actually sent)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("10.255.255.255", 1))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        pass  # windowed exe has no stderr; a dropped client must not crash a worker


class WebServer:
    def __init__(self, ctx: WebContext, web_dir, host: str = "0.0.0.0", port: int = 0):
        self.ctx = ctx
        self.web_dir = Path(web_dir).resolve()
        self.host = host
        self._requested_port = port
        self.token = secrets.token_urlsafe(16)
        self._httpd = None
        self._thread = None
        self._report_lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def port(self) -> int:
        return self._httpd.server_address[1] if self._httpd else 0

    def url(self, host: str) -> str:
        return f"http://{host}:{self.port}/?t={self.token}"

    def start(self) -> None:
        if self.running:
            return
        self._httpd = _Server((self.host, self._requested_port), _make_handler(self))
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, kwargs={"poll_interval": 0.05},
            name="peakview-web", daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        httpd, thread = self._httpd, self._thread
        if httpd is None:
            return
        httpd.shutdown()
        httpd.server_close()
        if thread is not None:
            thread.join(timeout=3)
        self._httpd = None
        self._thread = None


def _make_handler(web: WebServer):
    cookie_name = lambda: f"pv_{web.port}"  # noqa: E731  (port is known once bound)

    class Handler(BaseHTTPRequestHandler):
        server_version = "PeakView"
        sys_version = ""

        def log_message(self, fmt, *args):
            pass  # never log URLs: they may carry the token

        # --- response helpers -------------------------------------------

        def _send(self, status, body: bytes, ctype, extra=None):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", CSP)
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status, payload):
            self._send(status, json.dumps(payload).encode("utf-8"), MIME[".json"])

        def _error(self, status, code):
            self._json(status, {"error": code})

        # --- auth ---------------------------------------------------------

        def _token_ok(self, candidate) -> bool:
            return bool(candidate) and hmac.compare_digest(candidate.encode(), web.token.encode())

        def _authorized(self) -> bool:
            if self._token_ok(self.headers.get("X-Token", "")):
                return True
            raw = self.headers.get("Cookie")
            if raw:
                try:
                    jar = SimpleCookie(raw)
                except Exception:
                    return False
                morsel = jar.get(cookie_name())
                return morsel is not None and self._token_ok(morsel.value)
            return False

        # --- routing ------------------------------------------------------

        def do_GET(self):
            try:
                self._route_get()
            except Exception:
                self._error(500, "server_error")

        def do_POST(self):
            try:
                self._route_post()
            except Exception:
                self._error(500, "server_error")

        def _route_get(self):
            parts = urlsplit(self.path)
            path = unquote(parts.path)
            if not path.startswith("/api/") and self._try_login(parts):
                return
            if not self._authorized():
                return self._error(403, "forbidden")
            if path == "/api/state":
                return self._json(200, build_state(web.ctx))
            if path == "/api/summary":
                return self._json(200, build_summary(web.ctx))
            if path == "/api/timeline":
                return self._json(200, build_timeline(web.ctx, _since(parts.query)))
            if path == "/api/report.xlsx":
                return self._send_report()
            if path.startswith("/api/"):
                return self._error(404, "not_found")
            self._send_static(path)

        def _route_post(self):
            if not self._authorized():
                return self._error(403, "forbidden")
            if urlsplit(self.path).path != "/api/segment":
                return self._error(404, "not_found")
            body = self._read_json()
            if body is _REJECTED:
                return
            valid, changed = apply_segment(web.ctx, body)
            if not valid:
                return self._error(400, "invalid_segment")
            self._json(200, {"ok": True, "changed": changed, "state": build_state(web.ctx)})

        def _try_login(self, parts) -> bool:
            """?t=<token> on a page URL: set the cookie and redirect to a clean URL."""
            supplied = parse_qs(parts.query).get("t", [""])[0]
            if not self._token_ok(supplied):
                return False
            self.send_response(302)
            self.send_header("Location", "/")
            self.send_header(
                "Set-Cookie",
                f"{cookie_name()}={web.token}; Path=/; HttpOnly; SameSite=Strict",
            )
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return True

        def _read_json(self):
            if not self.headers.get("Content-Type", "").lower().startswith("application/json"):
                self._error(415, "unsupported_media_type")
                return _REJECTED
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                self._error(400, "bad_length")
                return _REJECTED
            if length < 0:
                self._error(400, "bad_length")
                return _REJECTED
            if length > MAX_BODY:
                self.close_connection = True
                self._error(413, "too_large")
                return _REJECTED
            try:
                return json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                self._error(400, "bad_json")
                return _REJECTED

        def _send_static(self, path):
            if "\\" in path or "\x00" in path:
                return self._error(404, "not_found")
            rel = "index.html" if path in ("", "/") else path.lstrip("/")
            target = (web.web_dir / rel).resolve()
            try:
                target.relative_to(web.web_dir)
            except ValueError:
                return self._error(403, "forbidden")
            if not target.is_file():
                return self._error(404, "not_found")
            ctype = MIME.get(target.suffix.lower(), "application/octet-stream")
            self._send(200, target.read_bytes(), ctype)

        def _send_report(self):
            builder = web.ctx.report_builder
            if builder is None:
                return self._error(404, "not_found")
            with web._report_lock:
                try:
                    path = Path(builder())
                except NoDataError:
                    return self._error(409, "no_data")
                except Exception:
                    return self._error(500, "report_failed")
                data = path.read_bytes()
            self._send(200, data, XLSX_MIME, {
                "Content-Disposition": f'attachment; filename="{path.name}"',
            })

    return Handler


_REJECTED = object()


def _since(query: str) -> int:
    try:
        return max(0, int(parse_qs(query).get("since", ["0"])[0]))
    except ValueError:
        return 0
