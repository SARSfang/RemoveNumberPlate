"""Open the bundled frontend in WebView2 and close after the load event."""

from __future__ import annotations

from app.desktop import smoke


def main() -> int:
    result = smoke()
    if result == 0:
        print("WebView2 frontend and Python bridge loaded successfully.")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
