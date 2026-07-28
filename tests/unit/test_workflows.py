from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_github_workflows_parse_as_yaml() -> None:
    workflows = PROJECT_ROOT / ".github" / "workflows"
    for path in sorted(workflows.glob("*.yml")):
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(parsed, dict), path
        assert parsed.get("jobs"), path
