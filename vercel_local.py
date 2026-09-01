"""Run the Vercel API and static site locally for pre-deployment testing."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def load_env() -> None:
    for raw in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


load_env()
from api.index import handler as VercelHandler  # noqa: E402


class LocalHandler(VercelHandler, SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        SimpleHTTPRequestHandler.__init__(self, *args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        if self.path.startswith("/api/"):
            return VercelHandler.do_GET(self)
        if self.path == "/admin":
            self.path = "/admin.html"
        elif self.path == "/login":
            self.path = "/login.html"
        return SimpleHTTPRequestHandler.do_GET(self)

    def do_POST(self):
        return VercelHandler.do_POST(self)

    def do_PATCH(self):
        return VercelHandler.do_PATCH(self)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("localhost", 8001), LocalHandler)
    print("Vercel-compatible local server running at http://localhost:8001")
    server.serve_forever()
