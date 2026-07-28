from app.infrastructure.webview2 import detect_webview2_version


def test_non_windows_has_no_webview2(monkeypatch) -> None:
    monkeypatch.setattr("app.infrastructure.webview2.sys.platform", "linux")

    assert detect_webview2_version() is None
