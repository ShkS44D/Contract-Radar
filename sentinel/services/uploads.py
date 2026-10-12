"""Isolated source preparation shared by browser, API, and CLI."""

from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import IO


class UploadError(ValueError):
    """User input does not satisfy the source upload policy."""


@dataclass(frozen=True)
class UploadPolicy:
    """Byte and archive limits, independent of request transport."""

    max_upload: int = 2 * 1024 * 1024
    max_extracted: int = 8 * 1024 * 1024
    max_files: int = 50
    max_ratio: int = 100


def validate_source(data: bytes) -> str:
    """Require nonempty UTF-8 text with no binary control characters."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UploadError("Solidity source must be UTF-8 text") from exc
    if not text.strip():
        raise UploadError("The source file is empty")
    if any(ord(char) < 32 and char not in "\r\n\t" for char in text) or "\x7f" in text:
        raise UploadError("Binary content is not allowed")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def prepare_upload(stream: IO[bytes], filename: str, temp_root: Path, policy: UploadPolicy) -> Path:
    """Copy a bounded source into a unique directory; callers own cleanup."""
    suffix = Path(filename).suffix.lower()
    if suffix != ".sol":
        raise UploadError("Upload a .sol file")
    data = stream.read(policy.max_upload + 1)
    if len(data) > policy.max_upload:
        raise UploadError("Upload exceeds the size limit")
    text = validate_source(data)
    temp_root.mkdir(parents=True, exist_ok=True)
    root = temp_root / str(uuid.uuid4())
    root.mkdir(mode=0o700)
    try:
        (root / f"{uuid.uuid4().hex}.sol").write_text(text, encoding="utf-8", newline="\n")
        return root
    except BaseException:
        shutil.rmtree(root)
        raise


def prepare_path(path: Path, temp_root: Path, policy: UploadPolicy) -> Path:
    """Prepare a CLI file or a directory of Solidity sources."""
    if not path.is_dir():
        with path.open("rb") as stream:
            return prepare_upload(stream, path.name, temp_root, policy)
    files = sorted(path.rglob("*.sol"))
    if not files or len(files) > policy.max_files:
        raise UploadError("Project must contain between 1 and the configured maximum source files")
    root = temp_root / str(uuid.uuid4())
    root.mkdir(parents=True, mode=0o700)
    try:
        total = 0
        for file in files:
            if file.is_symlink() or not file.resolve().is_relative_to(path.resolve()):
                raise UploadError("Symbolic links are not supported")
            data = file.read_bytes()
            total += len(data)
            if len(data) > policy.max_upload or total > policy.max_extracted:
                raise UploadError("Project exceeds source size limits")
            target = root / file.relative_to(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(validate_source(data), encoding="utf-8", newline="\n")
        return root
    except BaseException:
        shutil.rmtree(root)
        raise
