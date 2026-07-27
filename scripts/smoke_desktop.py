"""Open the bundled frontend in WebView2 and close after the load event."""

from __future__ import annotations

import threading

import webview

from app.desktop import DesktopApi, frontend_directory


class SmokeApi(DesktopApi):
    def __init__(self, ready: threading.Event) -> None:
        super().__init__()
        self._ready = ready

    def frontend_ready(self) -> bool:
        self._ready.set()
        if self._window is not None:
            threading.Timer(0.2, self._window.destroy).start()
        return True


def main() -> int:
    loaded = threading.Event()
    bridge_ready = threading.Event()
    api = SmokeApi(bridge_ready)
    window = webview.create_window(
        "消除车牌 · 启动检查",
        url=str(frontend_directory() / "index.html"),
        js_api=api,
        width=1040,
        height=680,
        min_size=(1040, 680),
        background_color="#0C111B",
    )
    if window is None:
        return 1
    api.bind_window(window)

    def close_after_load() -> None:
        loaded.set()

    window.events.loaded += close_after_load
    webview.start(gui="edgechromium", debug=False, private_mode=True)
    if loaded.is_set() and bridge_ready.is_set():
        print("WebView2 frontend and Python bridge loaded successfully.")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
