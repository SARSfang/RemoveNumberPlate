import re
import tomllib
from pathlib import Path

import app
from app.version import __version__, __windows_version__

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_release_version_is_synchronized() -> None:
    pyproject = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    installer = (PROJECT_ROOT / "packaging" / "installer.iss").read_text(
        encoding="utf-8"
    )
    version_info = (PROJECT_ROOT / "packaging" / "version_info.txt").read_text(
        encoding="utf-8"
    )
    release_notes = (PROJECT_ROOT / "RELEASE.md").read_text(encoding="utf-8")
    build_script = (
        PROJECT_ROOT / "packaging" / "build_release.ps1"
    ).read_text(encoding="utf-8")

    package_version = str(pyproject["project"]["version"]).replace("rc", "-rc.")
    assert package_version == __version__
    assert app.__version__ == __version__
    assert f'#define MyAppVersion "{__version__}"' in installer
    numeric = ".".join(str(value) for value in __windows_version__)
    assert f'#define MyNumericVersion "{numeric}"' in installer
    assert f"filevers={__windows_version__}" in version_info
    assert re.search(rf"v{re.escape(__version__)}\b", release_notes)
    assert '-Filter "*-Setup-v*-win64.exe"' in build_script
