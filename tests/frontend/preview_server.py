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
TARGET_IMAGE = ROOT / "docs" / "design" / "desktop-preview-workspace-option-2.png"
IMPLEMENTATION_IMAGE = (
    ROOT / "docs" / "audits" / "v0.2.0-rc.5" / "implementation-pass-2.png"
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
            markup = markup.replace('.css"', '.css?preview=16"')
            markup = markup.replace('.js"', '.js?preview=16"')
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
        if route == "/__preview__/target.png":
            self._send(TARGET_IMAGE.read_bytes(), "image/png")
            return
        if route == "/__preview__/implementation.png":
            self._send(IMPLEMENTATION_IMAGE.read_bytes(), "image/png")
            return
        if route == "/__preview__/comparison":
            markup = """<!doctype html>
<meta charset="utf-8">
<title>Desktop workspace design QA</title>
<style>
  * { box-sizing: border-box; }
  body { margin: 0; background: #060a10; color: #dce6f2;
    font: 14px/1.4 "Segoe UI", sans-serif; }
  header { height: 54px; display: flex; align-items: center; gap: 24px;
    padding: 0 22px; border-bottom: 1px solid #243143; }
  main { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; padding: 12px; }
  figure { margin: 0; min-width: 0; }
  figcaption { margin-bottom: 8px; color: #8fa0b6; }
  img { display: block; width: 100%; height: auto; border: 1px solid #243143; }
</style>
<header><strong>Desktop Preview Workspace</strong>
<span>same state · same 1487 × 1058 viewport · full-view comparison</span></header>
<main>
  <figure><figcaption>Target</figcaption>
    <img src="/__preview__/target.png" alt="Target design"></figure>
  <figure><figcaption>Implementation · pass 2</figcaption>
    <img src="/__preview__/implementation.png" alt="Implementation screenshot"></figure>
</main>"""
            self._send(markup.encode("utf-8"), "text/html; charset=utf-8")
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
