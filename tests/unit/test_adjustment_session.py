from pathlib import Path

import pytest

from app.core.adjustment_session import AdjustmentSessionManager


def _complete(
    manager: AdjustmentSessionManager,
    tmp_path: Path,
    *,
    job_id: str = "job-1",
    revision: str = "base",
) -> tuple[str, str]:
    generation = manager.begin(job_id, revision, [{"type": "set_margin", "value": 0.08}])
    cache = manager.cache_path(generation, ".jpg")
    cache.write_bytes(b"preview")
    session = manager.complete(
        generation,
        cache,
        width=100,
        height=50,
        elapsed_seconds=1.2,
    )
    assert session is not None
    return generation, session.preview_token


def test_session_token_is_bound_to_job_and_consumed(tmp_path: Path) -> None:
    manager = AdjustmentSessionManager(tmp_path / "cache")
    _generation, token = _complete(manager, tmp_path)

    session = manager.get("job-1", token)

    assert session.commands_digest
    with pytest.raises(ValueError, match="match"):
        manager.get("job-2", token)
    manager.finish(token)
    assert not session.cache_path.exists()
    with pytest.raises(ValueError, match="available"):
        manager.get("job-1", token)


def test_session_expires_and_cleans_cache(tmp_path: Path) -> None:
    now = 10.0
    manager = AdjustmentSessionManager(
        tmp_path / "cache",
        ttl_seconds=30,
        clock=lambda: now,
    )
    _generation, token = _complete(manager, tmp_path)
    now = 41.0

    with pytest.raises(ValueError, match="expired"):
        manager.get("job-1", token)

    assert not list((tmp_path / "cache").iterdir())


def test_new_preview_invalidates_old_token_and_late_render(tmp_path: Path) -> None:
    manager = AdjustmentSessionManager(tmp_path / "cache")
    old_generation, old_token = _complete(manager, tmp_path)
    new_generation = manager.begin("job-1", "base", [])
    late_cache = manager.cache_path(old_generation, ".png")
    late_cache.write_bytes(b"late")

    assert (
        manager.complete(
            old_generation,
            late_cache,
            width=1,
            height=1,
            elapsed_seconds=0,
        )
        is None
    )
    assert not late_cache.exists()
    with pytest.raises(ValueError):
        manager.get("job-1", old_token)
    assert manager.cancel("job-1")
    assert new_generation


def test_manager_cleans_orphans_on_start(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "orphan.jpg").write_bytes(b"old")

    AdjustmentSessionManager(cache_dir)

    assert not list(cache_dir.iterdir())
