import sqlite3
import time
from pathlib import Path

from app.core.job_store import JobStore, prepare_job_database
from app.domain.detection import Detection, Quadrilateral
from app.domain.job import JobStatus, RiskReason
from app.domain.result import ProcessingResult


def test_job_store_records_result_and_counts(tmp_path: Path) -> None:
    source = tmp_path / "source.jpg"
    polygon = Quadrilateral(((10, 20), (100, 18), (98, 50), (12, 52)))
    detection = Detection(polygon.bounding_box, 0.55, polygon=polygon)
    with JobStore(tmp_path / "jobs.sqlite3") as store:
        identifier = store.create_job(source)
        store.set_status(identifier, JobStatus.DETECTING)
        store.record_result(
            identifier,
            ProcessingResult(
                None,
                1,
                risks=(RiskReason.LOW_CONFIDENCE,),
                status=JobStatus.REVIEW_REQUIRED,
                detection_count=1,
                detections=(detection,),
            ),
        )

        jobs = store.list_jobs()

        assert jobs[0].status is JobStatus.REVIEW_REQUIRED
        assert jobs[0].risks == (RiskReason.LOW_CONFIDENCE,)
        assert jobs[0].detections == (detection,)
        assert jobs[0].elapsed_seconds == 1
        assert jobs[0].created_at
        assert jobs[0].updated_at
        assert store.counts() == {"review_required": 1}


def test_job_store_recovers_interrupted_state(tmp_path: Path) -> None:
    with JobStore(tmp_path / "jobs.sqlite3") as store:
        identifier = store.create_job(tmp_path / "source.jpg")
        store.set_status(identifier, JobStatus.INPAINTING)

        recovered = store.recover_interrupted()

        assert recovered == 1
        assert store.list_jobs()[0].status is JobStatus.QUEUED


def test_job_store_round_trips_latest_mask_revision(tmp_path: Path) -> None:
    with JobStore(tmp_path / "jobs.sqlite3") as store:
        identifier = store.create_job(tmp_path / "source.jpg")
        first = [{"type": "rectangle", "start": [1, 2], "end": [3, 4]}]
        second = [{"type": "brush_add", "points": [[5, 6]], "radius": 10}]

        store.record_mask_revision(identifier, first)
        store.record_mask_revision(identifier, second)

        assert store.latest_mask_revision(identifier) == second


def test_adjustment_result_preserves_detections_and_old_output(tmp_path: Path) -> None:
    source = tmp_path / "source.jpg"
    first_output = tmp_path / "source_clean.jpg"
    second_output = tmp_path / "source_clean_2.jpg"
    detection = Detection(
        Quadrilateral(((10, 20), (100, 18), (98, 50), (12, 52))).bounding_box,
        0.8,
        polygon=Quadrilateral(((10, 20), (100, 18), (98, 50), (12, 52))),
    )
    first_output.write_bytes(b"old")
    second_output.write_bytes(b"new")
    with JobStore(tmp_path / "jobs.sqlite3") as store:
        identifier = store.create_job(source)
        store.record_result(
            identifier,
            ProcessingResult(
                first_output,
                1,
                status=JobStatus.COMPLETED,
                detections=(detection,),
                detection_count=1,
            ),
        )

        revision = store.record_adjustment_result(
            identifier,
            second_output,
            [{"type": "set_margin", "value": 0.08}],
            elapsed_seconds=2,
        )
        job = store.get_job(identifier)
        revision_entry = store.latest_mask_revision_entry(identifier)

    assert first_output.read_bytes() == b"old"
    assert job.output == second_output
    assert job.detections == (detection,)
    assert job.status is JobStatus.COMPLETED
    assert revision_entry == (
        revision,
        [{"type": "set_margin", "value": 0.08}],
    )


def test_job_store_migrates_v1_database_without_losing_jobs(tmp_path: Path) -> None:
    database = tmp_path / "jobs.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE schema_info(version INTEGER NOT NULL)")
    connection.execute("INSERT INTO schema_info(version) VALUES (1)")
    connection.commit()
    connection.close()

    with JobStore(database) as store:
        identifier = store.create_job(tmp_path / "source.jpg")
        assert store.get_job(identifier).status is JobStatus.QUEUED

    connection = sqlite3.connect(database)
    version = connection.execute("SELECT version FROM schema_info").fetchone()
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    connection.close()
    assert version == (7,)
    assert {"jobs", "detections", "mask_revisions"} <= tables


def test_job_store_migrates_v3_detection_to_polygon_fallback(
    tmp_path: Path,
) -> None:
    database = tmp_path / "jobs.sqlite3"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE schema_info(version INTEGER NOT NULL);
        INSERT INTO schema_info(version) VALUES (3);
        CREATE TABLE jobs (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            output TEXT,
            status TEXT NOT NULL,
            risks_json TEXT NOT NULL DEFAULT '[]',
            error TEXT,
            elapsed_seconds REAL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE detections (
            job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            ordinal INTEGER NOT NULL,
            x1 REAL NOT NULL,
            y1 REAL NOT NULL,
            x2 REAL NOT NULL,
            y2 REAL NOT NULL,
            confidence REAL NOT NULL,
            source_tile INTEGER,
            PRIMARY KEY(job_id, ordinal)
        );
        CREATE TABLE mask_revisions (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            commands_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        INSERT INTO jobs(
            id, source, status, created_at, updated_at
        ) VALUES ('job-1', 'source.jpg', 'completed', 'now', 'now');
        INSERT INTO detections(
            job_id, ordinal, x1, y1, x2, y2, confidence
        ) VALUES ('job-1', 0, 10, 20, 100, 50, 0.9);
        """
    )
    connection.commit()
    connection.close()

    with JobStore(database) as store:
        job = store.get_job("job-1")
        store.verify_integrity()

    assert job.detections[0].polygon is None
    assert job.detections[0].effective_polygon == Quadrilateral(
        ((10, 20), (100, 20), (100, 50), (10, 50))
    )
    connection = sqlite3.connect(database)
    assert connection.execute("SELECT version FROM schema_info").fetchone() == (7,)
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(detections)")
    }
    connection.close()
    assert "polygon_json" in columns


def test_job_store_migrates_v4_to_v5_with_file_metadata(tmp_path: Path) -> None:
    """v4 库缺少 file_mtime/file_size 列，迁移到 v5 后应存在且旧 job 记录为 NULL。"""
    database = tmp_path / "jobs.sqlite3"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE schema_info(version INTEGER NOT NULL);
        INSERT INTO schema_info(version) VALUES (4);
        CREATE TABLE jobs (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            output TEXT,
            status TEXT NOT NULL,
            risks_json TEXT NOT NULL DEFAULT '[]',
            error TEXT,
            elapsed_seconds REAL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE detections (
            job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            ordinal INTEGER NOT NULL,
            x1 REAL NOT NULL,
            y1 REAL NOT NULL,
            x2 REAL NOT NULL,
            y2 REAL NOT NULL,
            confidence REAL NOT NULL,
            source_tile INTEGER,
            polygon_json TEXT,
            PRIMARY KEY(job_id, ordinal)
        );
        CREATE TABLE mask_revisions (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            commands_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        INSERT INTO jobs(id, source, status, created_at, updated_at)
        VALUES ('job-v4', 'source.jpg', 'completed', 'now', 'now');
        """
    )
    connection.commit()
    connection.close()

    # 迁移到 v5
    with JobStore(database) as store:
        job = store.get_job("job-v4")
        # 旧 job 的 file_mtime/file_size 应为 None（迁移前未记录）
        assert job.file_mtime is None
        assert job.file_size is None

    connection = sqlite3.connect(database)
    assert connection.execute("SELECT version FROM schema_info").fetchone() == (7,)
    job_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(jobs)")
    }
    connection.close()
    assert "file_mtime" in job_columns
    assert "file_size" in job_columns


def test_job_store_create_job_records_file_metadata(tmp_path: Path) -> None:
    """create_job 应自动记录文件 mtime/size（best-effort）。"""
    database = tmp_path / "jobs.sqlite3"
    source = tmp_path / "photo.jpg"
    source.write_bytes(b"\xff\xd8\xff\xe0")  # JPEG 头，可被 stat
    expected_mtime = source.stat().st_mtime
    expected_size = source.stat().st_size

    with JobStore(database) as store:
        identifier = store.create_job(source)
        job = store.get_job(identifier)

    assert job.file_mtime is not None
    assert job.file_size is not None
    assert abs(job.file_mtime - expected_mtime) < 1.0
    assert job.file_size == expected_size


def test_job_store_create_job_handles_missing_file(tmp_path: Path) -> None:
    """create_job 对不存在的 source 应容忍 stat 失败，metadata 留空。"""
    database = tmp_path / "jobs.sqlite3"
    source = tmp_path / "missing.jpg"

    with JobStore(database) as store:
        identifier = store.create_job(source)
        job = store.get_job(identifier)

    assert job.file_mtime is None
    assert job.file_size is None


def test_job_store_get_latest_by_source_returns_most_recent(tmp_path: Path) -> None:
    """同一路径多条记录时，get_latest_by_source 返回最新一条。"""
    database = tmp_path / "jobs.sqlite3"
    source = tmp_path / "photo.jpg"
    with JobStore(database) as store:
        # 第一张 job（较早）
        store.create_job(source)
        # 第二张 job（较晚，因为 created_at 由 datetime.now 生成）
        time.sleep(0.01)
        id2 = store.create_job(source)

        latest = store.get_latest_by_source(str(source.resolve()))
        assert latest is not None
        assert latest.id == id2


def test_job_store_get_latest_by_source_returns_none_when_empty(
    tmp_path: Path,
) -> None:
    """无记录时返回 None。"""
    database = tmp_path / "jobs.sqlite3"
    with JobStore(database) as store:
        assert store.get_latest_by_source("/nonexistent.jpg") is None


def test_job_store_get_latest_by_source_matches_resolved_path(
    tmp_path: Path,
) -> None:
    """create_job 内部 resolve 路径后存储；查询时用 resolve 后的字符串能查到。"""
    database = tmp_path / "jobs.sqlite3"
    source = tmp_path / "photo.jpg"
    with JobStore(database) as store:
        store.create_job(source)
        # create_job 内部用 str(source.resolve()) 存储
        latest = store.get_latest_by_source(str(source.resolve()))
        assert latest is not None
        assert latest.source == source.resolve()
        # 不存在的路径返回 None
        assert store.get_latest_by_source(str(tmp_path / "other.jpg")) is None


def test_prepare_job_database_quarantines_confirmed_corruption(
    tmp_path: Path,
) -> None:
    database = tmp_path / "jobs.sqlite3"
    corrupt_payload = b"this is not sqlite"
    database.write_bytes(corrupt_payload)

    backup = prepare_job_database(database)

    assert backup is not None
    assert backup.name.startswith("jobs.sqlite3.corrupt-")
    assert backup.read_bytes() == corrupt_payload
    with JobStore(database) as store:
        store.verify_integrity()
        assert store.counts() == {}


def test_prepare_job_database_does_not_quarantine_future_schema(
    tmp_path: Path,
) -> None:
    database = tmp_path / "jobs.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE schema_info(version INTEGER NOT NULL)")
    connection.execute("INSERT INTO schema_info(version) VALUES (999)")
    connection.commit()
    connection.close()

    try:
        prepare_job_database(database)
    except RuntimeError as error:
        assert "unsupported job database version" in str(error)
    else:
        raise AssertionError("future schema should be rejected")

    assert database.is_file()
    assert not list(tmp_path.glob("*.corrupt-*"))


def test_job_store_migrates_v5_to_v6_with_post_processed_output(
    tmp_path: Path,
) -> None:
    """v5 库缺少 post_processed_output 列，迁移到 v6 后应存在且旧 job 记录为 NULL。"""
    database = tmp_path / "jobs.sqlite3"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE schema_info(version INTEGER NOT NULL);
        INSERT INTO schema_info(version) VALUES (5);
        CREATE TABLE jobs (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            output TEXT,
            status TEXT NOT NULL,
            risks_json TEXT NOT NULL DEFAULT '[]',
            error TEXT,
            elapsed_seconds REAL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            file_mtime REAL,
            file_size INTEGER
        );
        CREATE TABLE detections (
            job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            ordinal INTEGER NOT NULL,
            x1 REAL NOT NULL,
            y1 REAL NOT NULL,
            x2 REAL NOT NULL,
            y2 REAL NOT NULL,
            confidence REAL NOT NULL,
            source_tile INTEGER,
            polygon_json TEXT,
            PRIMARY KEY(job_id, ordinal)
        );
        CREATE TABLE mask_revisions (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            commands_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        INSERT INTO jobs(
            id, source, status, created_at, updated_at,
            file_mtime, file_size
        ) VALUES ('job-v5', 'source.jpg', 'completed', 'now', 'now', 1.0, 100);
        """
    )
    connection.commit()
    connection.close()

    # 迁移到 v6
    with JobStore(database) as store:
        job = store.get_job("job-v5")
        # 旧 job 的 post_processed_output 应为 None（迁移前未记录）
        assert job.post_processed_output is None

    connection = sqlite3.connect(database)
    assert connection.execute("SELECT version FROM schema_info").fetchone() == (7,)
    job_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(jobs)")
    }
    connection.close()
    assert "post_processed_output" in job_columns


def test_job_store_set_post_processed_output_round_trip(
    tmp_path: Path,
) -> None:
    """set_post_processed_output 写入后 get_job 应能读回。"""
    database = tmp_path / "jobs.sqlite3"
    with JobStore(database) as store:
        identifier = store.create_job(tmp_path / "source.jpg")
        store.set_post_processed_output(identifier, "D:/out/final.jpg")

        job = store.get_job(identifier)
        assert job.post_processed_output == "D:/out/final.jpg"

    # 重新打开数据库验证持久化
    with JobStore(database) as store:
        job = store.get_job(identifier)
        assert job.post_processed_output == "D:/out/final.jpg"


def test_job_store_set_post_processed_output_none_clears_field(
    tmp_path: Path,
) -> None:
    """set_post_processed_output(None) 清空字段。"""
    database = tmp_path / "jobs.sqlite3"
    with JobStore(database) as store:
        identifier = store.create_job(tmp_path / "source.jpg")
        store.set_post_processed_output(identifier, "D:/out/final.jpg")
        store.set_post_processed_output(identifier, None)

        job = store.get_job(identifier)
        assert job.post_processed_output is None


def test_job_store_set_post_processed_output_unknown_id_raises(
    tmp_path: Path,
) -> None:
    """未知 identifier 应抛 KeyError。"""
    database = tmp_path / "jobs.sqlite3"
    with JobStore(database) as store:
        try:
            store.set_post_processed_output("nonexistent", "D:/out/final.jpg")
        except KeyError:
            pass
        else:
            raise AssertionError("expected KeyError for unknown identifier")


def test_job_store_create_job_with_post_processed_output(
    tmp_path: Path,
) -> None:
    """create_job 支持传入 post_processed_output 初始值。"""
    database = tmp_path / "jobs.sqlite3"
    source = tmp_path / "photo.jpg"
    source.write_bytes(b"\xff\xd8\xff\xe0")

    with JobStore(database) as store:
        identifier = store.create_job(
            source,
            post_processed_output="D:/out/initial.jpg",
        )
        job = store.get_job(identifier)

    assert job.post_processed_output == "D:/out/initial.jpg"


def test_job_store_list_jobs_includes_post_processed_output(
    tmp_path: Path,
) -> None:
    """list_jobs / get_latest_by_source 都应返回 post_processed_output 字段。"""
    database = tmp_path / "jobs.sqlite3"
    source = tmp_path / "photo.jpg"
    with JobStore(database) as store:
        identifier = store.create_job(source)
        store.set_post_processed_output(identifier, "D:/out/final.jpg")

        jobs = store.list_jobs()
        assert len(jobs) == 1
        assert jobs[0].post_processed_output == "D:/out/final.jpg"

        latest = store.get_latest_by_source(str(source.resolve()))
        assert latest is not None
        assert latest.post_processed_output == "D:/out/final.jpg"
