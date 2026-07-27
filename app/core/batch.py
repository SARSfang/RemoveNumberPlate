"""Sequential batch coordinator with per-image error isolation."""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.core.image_io import discover_images
from app.core.job_store import JobStore, StoredJob
from app.domain.job import JobStatus
from app.domain.result import ProcessingResult


class Processor(Protocol):
    def process(self, source: Path) -> ProcessingResult: ...


@dataclass(frozen=True, slots=True)
class BatchItemResult:
    source: Path
    result: ProcessingResult


@dataclass(frozen=True, slots=True)
class BatchReport:
    items: tuple[BatchItemResult, ...]
    elapsed_seconds: float

    def count(self, status: JobStatus) -> int:
        return sum(item.result.status is status for item in self.items)


def _process_sources(
    jobs: Sequence[tuple[str | None, Path]],
    processor: Processor,
    store: JobStore | None,
) -> BatchReport:
    start = time.perf_counter()
    results: list[BatchItemResult] = []
    for identifier, source in jobs:
        item_start = time.perf_counter()
        try:
            if store is not None and identifier is not None:
                store.set_status(identifier, JobStatus.DETECTING)
            result = processor.process(source)
        except Exception as error:
            result = ProcessingResult(
                None,
                time.perf_counter() - item_start,
                status=JobStatus.FAILED,
                error=f"{type(error).__name__}: {error}",
            )
        if store is not None and identifier is not None:
            store.record_result(identifier, result)
        results.append(BatchItemResult(source, result))
    return BatchReport(tuple(results), time.perf_counter() - start)


def process_batch(
    paths: list[Path],
    processor: Processor,
    store: JobStore | None = None,
) -> BatchReport:
    sources = discover_images(paths)
    jobs = [
        (store.create_job(source) if store is not None else None, source)
        for source in sources
    ]
    return _process_sources(jobs, processor, store)


def resume_batch(
    jobs: tuple[StoredJob, ...],
    processor: Processor,
    store: JobStore,
) -> BatchReport:
    pending = [(job.id, job.source) for job in jobs if job.status is JobStatus.QUEUED]
    return _process_sources(pending, processor, store)
