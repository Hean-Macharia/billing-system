import os
import re
from pathlib import Path
from urllib.parse import urlparse, urlencode, urlunparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import request as urllib_request

ROOT = Path(__file__).resolve().parent
BACKEND_BASE = "http://127.0.0.1:8000"
PORT = 8080


def static_dir(name: str) -> Path:
    return ROOT / name


class AppProxyHandler(BaseHTTPRequestHandler):
    server_version = "ISPProxy/1.0"

    def log_message(self, format, *args):
        return

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_PATCH(self):
        self._dispatch("PATCH")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def do_OPTIONS(self):
        self._dispatch("OPTIONS")

    def _dispatch(self, method):
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/") or path == "/api":
            self._proxy_request(method, parsed)
            return

        if path in ("", "/"):
            self._redirect("/hotspot/")
            return

        if path.startswith("/admin"):
            self._serve_static("admin", path.replace("/admin", "", 1))
            return

        if path.startswith("/portal"):
            self._serve_static("portal", path.replace("/portal", "", 1))
            return

        if path.startswith("/hotspot"):
            self._serve_static("hotspot", path.replace("/hotspot", "", 1))
            return

        if path.startswith("/assets/"):
            self._serve_static("admin", path)
            return

        self._redirect("/hotspot/")

    def _proxy_request(self, method, parsed):
        target_path = parsed.path
        if target_path in {"/api", "/api/"}:
            target_path = "/"

        upstream_url = BACKEND_BASE + target_path
        if parsed.query:
            upstream_url += "?" + parsed.query

        data = None
        headers = {k: v for k, v in self.headers.items() if k.lower() not in {"host", "content-length"}}

        if method in {"POST", "PUT", "PATCH", "DELETE"}:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length > 0:
                data = self.rfile.read(content_length)

        req = urllib_request.Request(upstream_url, data=data, headers=headers, method=method)
        try:
            with urllib_request.urlopen(req, timeout=20) as resp:
                body = resp.read()
                self._send_upstream_response(resp.status, resp.headers.items(), body)
        except urllib_request.HTTPError as exc:
            body = exc.read()
            self._send_upstream_response(exc.code, exc.headers.items(), body)
        except Exception as exc:
            payload = f"Proxy error: {exc}".encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    def _send_upstream_response(self, status, headers, body):
        self.send_response(status)
        for key, value in headers:
            if key.lower() in {"transfer-encoding", "content-encoding", "content-length"}:
                continue
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _redirect(self, location: str):
        self.send_response(301)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _serve_static(self, app_name: str, request_path: str):
        app_dir = static_dir(app_name)
        if request_path in ("", "/"):
            candidate = app_dir / "index.html"
        else:
            candidate = (app_dir / request_path.lstrip("/")).resolve()
            try:
                candidate.relative_to(app_dir.resolve())
            except ValueError:
                self.send_error(403, "Forbidden")
                return

        if candidate.is_dir():
            index = candidate / "index.html"
            if index.exists():
                candidate = index
            else:
                self.send_error(404, "Not Found")
                return

        if not candidate.exists() or not candidate.is_file():
            self.send_error(404, "Not Found")
            return

        ext = candidate.suffix.lower()
        mime_types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon",
            ".txt": "text/plain; charset=utf-8",
        }
        content_type = mime_types.get(ext, "application/octet-stream")
        body = candidate.read_bytes()

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), AppProxyHandler)
    print(f"Local ISP proxy running on http://127.0.0.1:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
