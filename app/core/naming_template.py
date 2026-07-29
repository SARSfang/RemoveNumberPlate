"""Parse and render filename templates for batch post-processing.

Supports placeholders {original}, {ext}, {seq}, {client}, {date}.
Windows-illegal characters in rendered output are replaced with underscores.
Empty or whitespace-only results fall back to the default template.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TEMPLATE = "{original}_clean{ext}"

_PLACEHOLDER_RE = re.compile(r"\{(\w+)(?::([^}]+))?\}")
_ILLEGAL_CHAR_RE = re.compile(r'[<>:"/\\|?*]')


def _format_sequence(sequence: int, spec: str | None) -> str:
    if spec is None:
        return str(sequence)
    match = re.fullmatch(r"0*(\d+)d?", spec)
    if match:
        width = int(match.group(1))
        return str(sequence).zfill(width)
    return format(sequence, spec)


@dataclass(frozen=True, slots=True)
class NamingContext:
    """Context values substituted into a naming template."""

    original_stem: str
    extension: str
    sequence: int
    client: str
    shot_date: str


class NamingTemplate:
    """Parse and render filename templates."""

    def __init__(self, template: str) -> None:
        self._template = template

    def _render_raw(self, template: str, context: NamingContext) -> str:
        def replacer(match: re.Match[str]) -> str:
            field = match.group(1)
            spec = match.group(2)
            if field == "original":
                return context.original_stem
            if field == "ext":
                return context.extension
            if field == "seq":
                return _format_sequence(context.sequence, spec)
            if field == "client":
                return context.client
            if field == "date":
                return context.shot_date
            return match.group(0)

        return _PLACEHOLDER_RE.sub(replacer, template)

    def render(self, context: NamingContext) -> str:
        template = self._template if self._template.strip() else DEFAULT_TEMPLATE
        rendered = _ILLEGAL_CHAR_RE.sub("_", self._render_raw(template, context))
        if not rendered.strip():
            rendered = _ILLEGAL_CHAR_RE.sub("_", self._render_raw(DEFAULT_TEMPLATE, context))
        return rendered

    def resolve_conflict(self, directory: Path, filename: str) -> Path:
        """Return a non-conflicting full path. filename includes extension.

        If the target file already exists, insert _2, _3, ... before the
        extension until a free name is found.
        """
        target = directory / filename
        if not target.exists():
            return target
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        counter = 2
        while True:
            candidate = directory / f"{stem}_{counter}{suffix}"
            if not candidate.exists():
                return candidate
            counter += 1
