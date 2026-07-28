"""Serve the production desktop frontend with a test-only WebView bridge."""

from __future__ import annotations

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "app" / "web"
MOCK_BRIDGE = ROOT / "tests" / "frontend" / "workspace-preview-bridge.js"
SOURCE_IMAGE = ROOT / "testdata" / "public" / "ppvehicleplate.jpg"
RESULT_IMAGE = (
    ROOT / "testdata" / "public" / "车牌已消除" / "ppvehicleplate_clean.jpg"
)


class PreviewHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        route = self.path.partition("?")[0]
        if route in {"/", "/index.html"}:
            markup = (WEB / "index.html").read_text(encoding="utf-8")
            markup = markup.replace(
                '<script defer src="core/state.js"></script>',
                '<script src="/__preview__/bridge.js"></script>\n'
                '  <script defer src="core/state.js"></script>',
                1,
            )
            markup = markup.replace('.css"', '.css?preview=5"')
            markup = markup.replace('.js"', '.js?preview=5"')
            self._send(markup.encode("utf-8"), "text/html; charset=utf-8")
            return
        if route == "/__preview__/bridge.js":
            self._send(MOCK_BRIDGE.read_bytes(), "text/javascript; charset=utf-8")
            return
        if route == "/__preview__/source.jpg":
            self._send(SOURCE_IMAGE.read_bytes(), "image/jpeg")
            return
        if route == "/__preview__/result.jpg":
            self._send(RESULT_IMAGE.read_bytes(), "image/jpeg")
            return
        self.directory = str(WEB)
        super().do_GET()

    def _send(self, payload: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 59032), PreviewHandler).serve_forever()
