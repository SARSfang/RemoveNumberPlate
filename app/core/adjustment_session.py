"""Single-user local preview sessions for manual plate adjustments."""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AdjustmentSession:
    job_id: str
    revision: str
    commands_json: str
    commands_digest: str
    preview_token: str
    cache_path: Path
    created_at: float
    width: int
    height: int
    elapsed_seconds: float

    @property
    def commands(self) -> list[dict[str, object]]:
        value = json.loads(self.commands_json)
        if not isinstance(value, list):
            raise RuntimeError("invalid adjustment session commands")
        return value


@dataclass(frozen=True, slots=True)
class _PendingAdjustment:
    generation: str
    job_id: str
    revision: str
    commands_json: str
    commands_digest: str


class AdjustmentSessionManager:
    """Own at most one pending render or saveable preview."""

    def __init__(
        self,
        cache_dir: Path,
        *,
        ttl_seconds: float = 30 * 60,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("preview TTL must be positive")
        self._cache_dir = cache_dir
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._pending: _PendingAdjustment | None = None
        self._session: AdjustmentSession | None = None
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self.cleanup_orphans()

    @staticmethod
    def _serialize(commands: Sequence[Mapping[str, object]]) -> tuple[str, str]:
        value = json.dumps(
            list(commands),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return value, hashlib.sha256(value.encode("utf-8")).hexdigest()

    def begin(
        self,
        job_id: str,
        revision: str,
        commands: Sequence[Mapping[str, object]],
    ) -> str:
        commands_json, digest = self._serialize(commands)
        generation = secrets.token_urlsafe(18)
        with self._lock:
            self._discard_session_locked()
            self._pending = _PendingAdjustment(
                generation,
                job_id,
                revision,
                commands_json,
                digest,
            )
        return generation

    def cache_path(self, generation: str, suffix: str) -> Path:
        safe_suffix = suffix.lower()
        if safe_suffix not in {".jpg", ".jpeg", ".png", ".tif", ".tiff"}:
            safe_suffix = ".png"
        return self._cache_dir / f"{generation}{safe_suffix}"

    def complete(
        self,
        generation: str,
        cache_path: Path,
        *,
        width: int,
        height: int,
        elapsed_seconds: float,
    ) -> AdjustmentSession | None:
        with self._lock:
            pending = self._pending
            if pending is None or pending.generation != generation:
                cache_path.unlink(missing_ok=True)
                return None
            self._pending = None
            session = AdjustmentSession(
                job_id=pending.job_id,
                revision=pending.revision,
                commands_json=pending.commands_json,
                commands_digest=pending.commands_digest,
                preview_token=secrets.token_urlsafe(32),
                cache_path=cache_path,
                created_at=self._clock(),
                width=width,
                height=height,
                elapsed_seconds=elapsed_seconds,
            )
            self._session = session
            return session

    def get(self, job_id: str, preview_token: str) -> AdjustmentSession:
        with self._lock:
            session = self._session
            if session is None:
                raise ValueError("preview is no longer available")
            if self._clock() - session.created_at > self._ttl_seconds:
                self._discard_session_locked()
                raise ValueError("preview has expired")
            if (
                not secrets.compare_digest(session.job_id, job_id)
                or not secrets.compare_digest(session.preview_token, preview_token)
            ):
                raise ValueError("preview token does not match this job")
            if not session.cache_path.is_file():
                self._session = None
                raise ValueError("preview cache is missing")
            return session

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            matched = False
            if self._pending is not None and self._pending.job_id == job_id:
                self._pending = None
                matched = True
            if self._session is not None and self._session.job_id == job_id:
                self._discard_session_locked()
                matched = True
            return matched

    def finish(self, preview_token: str) -> None:
        with self._lock:
            if (
                self._session is not None
                and secrets.compare_digest(
                    self._session.preview_token,
                    preview_token,
                )
            ):
                self._discard_session_locked()

    def _discard_session_locked(self) -> None:
        if self._session is not None:
            self._session.cache_path.unlink(missing_ok=True)
        self._session = None

    def cleanup_orphans(self) -> None:
        for candidate in self._cache_dir.iterdir():
            if candidate.is_file():
                with suppress(OSError):
                    candidate.unlink()
