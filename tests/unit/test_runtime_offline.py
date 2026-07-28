import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_NETWORK_MODULES = {
    "aiohttp",
    "http.client",
    "httpx",
    "requests",
    "socket",
    "urllib.request",
}


def test_application_runtime_imports_no_network_client() -> None:
    violations: list[str] = []
    for path in sorted((PROJECT_ROOT / "app").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue
            for module in modules:
                if any(
                    module == forbidden or module.startswith(f"{forbidden}.")
                    for forbidden in FORBIDDEN_NETWORK_MODULES
                ):
                    violations.append(f"{path.relative_to(PROJECT_ROOT)}: {module}")
    assert violations == []
