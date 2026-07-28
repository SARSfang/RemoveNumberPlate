from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_github_workflows_parse_as_yaml() -> None:
    workflows = PROJECT_ROOT / ".github" / "workflows"
    for path in sorted(workflows.glob("*.yml")):
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(parsed, dict), path
        assert parsed.get("jobs"), path


def test_release_workflow_creates_build_script_virtual_environment() -> None:
    workflow = (
        PROJECT_ROOT / ".github" / "workflows" / "release.yml"
    ).read_text(encoding="utf-8")

    create = "python -m venv .venv"
    install = r".\.venv\Scripts\python.exe -m pip install"
    build = r".\packaging\build_release.ps1"
    assert create in workflow
    assert install in workflow
    assert workflow.index(create) < workflow.index(install) < workflow.index(build)
