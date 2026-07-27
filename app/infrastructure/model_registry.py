"""Versioned model manifest loading and integrity checks."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ModelManifestError(ValueError):
    """The model manifest is missing, malformed, or unsafe."""


@dataclass(frozen=True, slots=True)
class ModelArtifact:
    model_id: str
    version: str
    filename: str
    sha256: str
    source_url: str
    homepage: str
    format: str
    software_license: str
    weights_terms: str
    enabled: bool

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> ModelArtifact:
        required = {
            "model_id",
            "version",
            "filename",
            "sha256",
            "source_url",
            "homepage",
            "format",
            "software_license",
            "weights_terms",
            "enabled",
        }
        missing = required.difference(value)
        if missing:
            raise ModelManifestError(f"missing model fields: {sorted(missing)}")

        artifact = cls(
            model_id=str(value["model_id"]),
            version=str(value["version"]),
            filename=str(value["filename"]),
            sha256=str(value["sha256"]).lower(),
            source_url=str(value["source_url"]),
            homepage=str(value["homepage"]),
            format=str(value["format"]),
            software_license=str(value["software_license"]),
            weights_terms=str(value["weights_terms"]),
            enabled=bool(value["enabled"]),
        )
        artifact._validate()
        return artifact

    def _validate(self) -> None:
        if Path(self.filename).name != self.filename:
            raise ModelManifestError("model filename must not contain a path")
        if self.enabled and len(self.sha256) != 64:
            raise ModelManifestError("enabled model must have a 64-character SHA-256")
        if self.sha256 and any(character not in "0123456789abcdef" for character in self.sha256):
            raise ModelManifestError("model SHA-256 must be lowercase hexadecimal")
        if self.enabled and not self.source_url.startswith("https://"):
            raise ModelManifestError("enabled model must use an HTTPS source URL")

    def verify(self, path: Path, chunk_size: int = 1024 * 1024) -> bool:
        if not self.enabled or not path.is_file():
            return False
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(chunk_size), b""):
                digest.update(chunk)
        return digest.hexdigest() == self.sha256


def load_manifest(path: Path) -> tuple[ModelArtifact, ...]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ModelManifestError(f"model manifest not found: {path}") from error
    except json.JSONDecodeError as error:
        raise ModelManifestError(f"invalid model manifest JSON: {error}") from error

    if data.get("schema_version") != 1:
        raise ModelManifestError("unsupported model manifest schema")
    models = data.get("models")
    if not isinstance(models, list):
        raise ModelManifestError("models must be a list")
    artifacts = tuple(ModelArtifact.from_mapping(item) for item in models)
    identifiers = [artifact.model_id for artifact in artifacts]
    if len(identifiers) != len(set(identifiers)):
        raise ModelManifestError("model_id values must be unique")
    return artifacts
