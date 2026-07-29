"""Unit tests for HistorySearchService."""

from __future__ import annotations

from pathlib import Path

from app.core.history_search import HistoryQuery, HistorySearchService
from app.core.job_store import JobStore
from app.domain.job import JobStatus


def _make_job(
    store: JobStore,
    source: Path,
    *,
    status: JobStatus = JobStatus.COMPLETED,
    created_at: str = "2026-07-15T10:00:00+00:00",
    project_id: str | None = None,
) -> str:
    """Create a job with controlled attributes for testing."""
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"fake")
    job_id = store.create_job(source)
    store.set_status(job_id, status)
    with store._connection:
        store._connection.execute(
            "UPDATE jobs SET created_at = ?, project_id = ? WHERE id = ?",
            (created_at, project_id, job_id),
        )
    return job_id


def test_search_no_filters_returns_all(tmp_path: Path) -> None:
    db = tmp_path / "jobs.sqlite3"
    with JobStore(db) as store:
        _make_job(store, tmp_path / "alpha.jpg")
        _make_job(store, tmp_path / "beta.jpg")
        _make_job(store, tmp_path / "gamma.jpg")

    service = HistorySearchService(db)
    results = service.search(HistoryQuery())

    assert len(results) == 3


def test_search_by_single_status(tmp_path: Path) -> None:
    db = tmp_path / "jobs.sqlite3"
    with JobStore(db) as store:
        _make_job(store, tmp_path / "a.jpg", status=JobStatus.COMPLETED)
        _make_job(store, tmp_path / "b.jpg", status=JobStatus.FAILED)
        _make_job(store, tmp_path / "c.jpg", status=JobStatus.COMPLETED)

    service = HistorySearchService(db)
    results = service.search(HistoryQuery(statuses=("completed",)))

    assert len(results) == 2
    assert all(job.status is JobStatus.COMPLETED for job in results)


def test_search_by_multiple_statuses(tmp_path: Path) -> None:
    db = tmp_path / "jobs.sqlite3"
    with JobStore(db) as store:
        _make_job(store, tmp_path / "a.jpg", status=JobStatus.COMPLETED)
        _make_job(store, tmp_path / "b.jpg", status=JobStatus.FAILED)
        _make_job(store, tmp_path / "c.jpg", status=JobStatus.QUEUED)

    service = HistorySearchService(db)
    results = service.search(
        HistoryQuery(statuses=("completed", "failed"))
    )

    assert len(results) == 2
    statuses = {job.status for job in results}
    assert statuses == {JobStatus.COMPLETED, JobStatus.FAILED}


def test_search_by_date_range(tmp_path: Path) -> None:
    db = tmp_path / "jobs.sqlite3"
    with JobStore(db) as store:
        _make_job(
            store, tmp_path / "early.jpg", created_at="2026-07-10T08:00:00+00:00"
        )
        _make_job(
            store, tmp_path / "mid.jpg", created_at="2026-07-15T12:00:00+00:00"
        )
        _make_job(
            store, tmp_path / "late.jpg", created_at="2026-07-25T18:00:00+00:00"
        )

    service = HistorySearchService(db)
    results = service.search(
        HistoryQuery(date_from="2026-07-12", date_to="2026-07-18")
    )

    assert len(results) == 1
    assert results[0].source.name == "mid.jpg"


def test_search_by_name_contains_case_insensitive(tmp_path: Path) -> None:
    db = tmp_path / "jobs.sqlite3"
    with JobStore(db) as store:
        _make_job(store, tmp_path / "IMG_001.jpg")
        _make_job(store, tmp_path / "img_002.jpg")
        _make_job(store, tmp_path / "photo.png")

    service = HistorySearchService(db)
    results = service.search(HistoryQuery(name_contains="img_00"))

    assert len(results) == 2
    names = {job.source.name for job in results}
    assert names == {"IMG_001.jpg", "img_002.jpg"}


def test_search_by_project_ids(tmp_path: Path) -> None:
    db = tmp_path / "jobs.sqlite3"
    with JobStore(db) as store:
        _make_job(store, tmp_path / "a.jpg", project_id="p1")
        _make_job(store, tmp_path / "b.jpg", project_id="p2")
        _make_job(store, tmp_path / "c.jpg", project_id="p1")
        _make_job(store, tmp_path / "d.jpg", project_id="p3")

    service = HistorySearchService(db)
    results = service.search(
        HistoryQuery(project_ids=("p1", "p3"), include_no_project=False)
    )

    assert len(results) == 3
    names = {job.source.name for job in results}
    assert names == {"a.jpg", "c.jpg", "d.jpg"}


def test_search_include_no_project(tmp_path: Path) -> None:
    db = tmp_path / "jobs.sqlite3"
    with JobStore(db) as store:
        _make_job(store, tmp_path / "a.jpg", project_id="p1")
        _make_job(store, tmp_path / "b.jpg", project_id=None)
        _make_job(store, tmp_path / "c.jpg", project_id="p2")

    service = HistorySearchService(db)
    results = service.search(
        HistoryQuery(project_ids=("p1",), include_no_project=True)
    )

    assert len(results) == 2
    names = {job.source.name for job in results}
    assert names == {"a.jpg", "b.jpg"}


def test_search_exclude_no_project(tmp_path: Path) -> None:
    db = tmp_path / "jobs.sqlite3"
    with JobStore(db) as store:
        _make_job(store, tmp_path / "a.jpg", project_id="p1")
        _make_job(store, tmp_path / "b.jpg", project_id=None)
        _make_job(store, tmp_path / "c.jpg", project_id="p2")
        _make_job(store, tmp_path / "d.jpg", project_id=None)

    service = HistorySearchService(db)
    results = service.search(HistoryQuery(include_no_project=False))

    assert len(results) == 2
    names = {job.source.name for job in results}
    assert names == {"a.jpg", "c.jpg"}


def test_search_limit_and_offset(tmp_path: Path) -> None:
    db = tmp_path / "jobs.sqlite3"
    with JobStore(db) as store:
        for i in range(5):
            _make_job(
                store,
                tmp_path / f"job_{i}.jpg",
                created_at=f"2026-07-{10 + i}T10:00:00+00:00",
            )

    service = HistorySearchService(db)
    page1 = service.search(HistoryQuery(limit=2, offset=0))
    page2 = service.search(HistoryQuery(limit=2, offset=2))

    assert len(page1) == 2
    assert len(page2) == 2
    # ORDER BY created_at DESC: job_4, job_3, job_2, job_1, job_0
    assert page1[0].source.name == "job_4.jpg"
    assert page1[1].source.name == "job_3.jpg"
    assert page2[0].source.name == "job_2.jpg"
    assert page2[1].source.name == "job_1.jpg"


def test_count_ignores_limit_offset(tmp_path: Path) -> None:
    db = tmp_path / "jobs.sqlite3"
    with JobStore(db) as store:
        for i in range(5):
            _make_job(
                store,
                tmp_path / f"job_{i}.jpg",
                created_at=f"2026-07-{10 + i}T10:00:00+00:00",
            )

    service = HistorySearchService(db)
    count = service.count(HistoryQuery(limit=2, offset=0))

    assert count == 5


def test_search_empty_database(tmp_path: Path) -> None:
    db = tmp_path / "jobs.sqlite3"
    with JobStore(db):
        pass

    service = HistorySearchService(db)
    results = service.search(HistoryQuery())
    count = service.count(HistoryQuery())

    assert results == []
    assert count == 0


def test_search_with_chinese_name(tmp_path: Path) -> None:
    db = tmp_path / "jobs.sqlite3"
    with JobStore(db) as store:
        _make_job(store, tmp_path / "测试车牌.jpg")
        _make_job(store, tmp_path / "normal.jpg")
        _make_job(store, tmp_path / "另一个测试.png")

    service = HistorySearchService(db)
    results = service.search(HistoryQuery(name_contains="测试"))

    assert len(results) == 2
    names = {job.source.name for job in results}
    assert names == {"测试车牌.jpg", "另一个测试.png"}
