from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_preview_build_uses_stable_isolated_output() -> None:
    script = (ROOT / "packaging" / "build_preview.ps1").read_text(encoding="utf-8")

    assert '--distpath $PreviewVersionDirectory' in script
    assert "--workpath build\\preview" in script
    assert "Get-ChildItem -LiteralPath $PreviewVersionDirectory" in script
    assert "$PreviewExecutables.Count -ne 1" in script
    assert '"--smoke"' in script
    assert "BUILD.txt" in script
    assert "CURRENT.txt" in script
    assert "Inno" not in script


def test_preview_launcher_never_installs_or_uninstalls() -> None:
    launcher = (ROOT / "启动测试版.cmd").read_text(encoding="utf-8")

    assert 'for /r "%~dp0dist\\preview"' in launcher
    assert "CURRENT.txt" in launcher
    assert "%APP_VERSION%" in launcher
    assert "start" in launcher.lower()
    assert "setup" not in launcher.lower()
    assert "uninstall" not in launcher.lower()


def test_release_build_ignores_preview_executable() -> None:
    script = (ROOT / "packaging" / "build_release.ps1").read_text(encoding="utf-8")

    # The release payload scan must exclude auxiliary build directories.
    # "hd-component" holds the optional HD runtime that the release merges
    # into the PyInstaller output directory before installer compilation.
    for excluded in ("installer", "preview", "hd-component", "hd-preview-final"):
        assert f'"{excluded}"' in script
    assert "$ReleaseDirectories.Count -ne 1" in script


def test_release_build_merges_hd_runtime_into_installer_payload() -> None:
    script = (ROOT / "packaging" / "build_release.ps1").read_text(encoding="utf-8")

    # installer.iss bundles dist\消除车牌\* recursively, so the HD runtime
    # only reaches users if it is merged into that directory.
    assert "[switch]$SkipHdRuntime" in script
    assert '"dist\\hd-component\\hd-runtime"' in script
    assert "_internal\\models\\big-lama.pt" in script
    assert "third_party_licenses_hd" in script
    assert "高清组件说明.md" in script
