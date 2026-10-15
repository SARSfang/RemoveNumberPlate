"""Exercise publication and rollback entirely inside a temporary directory."""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest

from scripts import deploy_product_site as deploy


def prepare(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "production" / "remove-number-plate"
    target.mkdir(parents=True)
    for name in deploy.ALLOWED:
        dest = target / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"old")
    (target.parent / "unrelated-site.html").write_bytes(b"untouched")
    stage = tmp_path / "stage"
    stage.mkdir()
    monkeypatch.setattr(deploy, "TARGET", target)
    monkeypatch.setattr(deploy, "STAGE_ROOT", stage)
    monkeypatch.setattr(deploy, "RECORD_ROOT", tmp_path / "records")
    return target


def package(tmp_path: Path, target: Path, *, unsafe: bool = False) -> Path:
    archive = tmp_path / "product.tar.gz"
    files = {name: hashlib.sha256(b"new").hexdigest() for name in deploy.ALLOWED}
    manifest = {"files": files, "expected": {
        name: deploy.digest(target / name) for name in ("index.html", "styles.css", "site.js")
    }}
    contents = {"product/" + name: b"new" for name in files}
    contents["manifest.json"] = json.dumps(manifest).encode()
    if unsafe:
        contents["../outside.html"] = b"bad"
    with tarfile.open(archive, "w:gz") as tar:
        for name, data in contents.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return archive


def test_deploy_keeps_backup_and_other_sites(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = prepare(tmp_path, monkeypatch)
    archive = package(tmp_path, target)
    monkeypatch.setattr("sys.argv", ["deploy", str(archive), "1001"])
    deploy.main()
    assert all((target / name).read_bytes() == b"new" for name in deploy.ALLOWED)
    assert (target.with_name(target.name + ".before-1001") / "index.html").read_bytes() == b"old"
    assert (target.parent / "unrelated-site.html").read_bytes() == b"untouched"
    assert (tmp_path / "records/rnp-product-1001/release.json").exists()


def test_deploy_rejects_changed_baseline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = prepare(tmp_path, monkeypatch)
    archive = package(tmp_path, target)
    (target / "index.html").write_bytes(b"someone else's edit")
    monkeypatch.setattr("sys.argv", ["deploy", str(archive), "1002"])
    with pytest.raises(ValueError, match="Production changed"):
        deploy.main()
    assert (target / "index.html").read_bytes() == b"someone else's edit"
    assert not target.with_name(target.name + ".before-1002").exists()


def test_deploy_rejects_archive_traversal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = prepare(tmp_path, monkeypatch)
    archive = package(tmp_path, target, unsafe=True)
    monkeypatch.setattr("sys.argv", ["deploy", str(archive), "1003"])
    with pytest.raises(ValueError, match="Unexpected archive member"):
        deploy.main()
    assert (target / "index.html").read_bytes() == b"old"
    assert not (tmp_path / "stage/outside.html").exists()


def test_deploy_restores_previous_on_switch_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = prepare(tmp_path, monkeypatch)
    archive = package(tmp_path, target)
    monkeypatch.setattr("sys.argv", ["deploy", str(archive), "1004"])
    rename = deploy.os.rename

    def fail_candidate(source: Path, destination: Path) -> None:
        if str(source).endswith(".candidate-1004"):
            raise OSError("simulated directory switch failure")
        rename(source, destination)

    monkeypatch.setattr(deploy.os, "rename", fail_candidate)
    with pytest.raises(OSError, match="simulated"):
        deploy.main()
    assert all((target / name).read_bytes() == b"old" for name in deploy.ALLOWED)
    assert (target.parent / "unrelated-site.html").read_bytes() == b"untouched"


def test_deploy_restores_previous_after_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = prepare(tmp_path, monkeypatch)
    archive = package(tmp_path, target)
    monkeypatch.setattr("sys.argv", ["deploy", str(archive), "1005"])
    write_text = Path.write_text

    def fail_record(path: Path, data: str) -> int:
        if path.name == "release.json":
            raise OSError("simulated record write failure")
        return write_text(path, data)

    monkeypatch.setattr(Path, "write_text", fail_record)
    with pytest.raises(OSError, match="simulated"):
        deploy.main()
    assert all((target / name).read_bytes() == b"old" for name in deploy.ALLOWED)
    assert (target.with_name(target.name + ".failed-1005") / "index.html").read_bytes() == b"new"
