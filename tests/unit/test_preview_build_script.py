from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_preview_build_uses_stable_isolated_output() -> None:
    script = (ROOT / "packaging" / "build_preview.ps1").read_text(encoding="utf-8")

    assert "--distpath dist\\preview" in script
    assert "--workpath build\\preview" in script
    assert 'Get-ChildItem -LiteralPath "dist\\preview"' in script
    assert "$PreviewExecutables.Count -ne 1" in script
    assert '"--smoke"' in script
    assert "BUILD.txt" in script
    assert "Inno" not in script


def test_preview_launcher_never_installs_or_uninstalls() -> None:
    launcher = (ROOT / "启动测试版.cmd").read_text(encoding="utf-8")

    assert 'for /r "%~dp0dist\\preview"' in launcher
    assert "start" in launcher.lower()
    assert "setup" not in launcher.lower()
    assert "uninstall" not in launcher.lower()


def test_release_build_ignores_preview_executable() -> None:
    script = (ROOT / "packaging" / "build_release.ps1").read_text(encoding="utf-8")

    assert '@("installer", "preview")' in script
    assert "$ReleaseDirectories.Count -ne 1" in script
