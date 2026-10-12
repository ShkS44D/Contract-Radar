"""Isolated source preparation shared by browser, API, and CLI."""

from __future__ import annotations

import io
import re
import shutil
import stat
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
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
    from contract_radar.scanner.source import mask_source

    if not re.search(
        r"\b(pragma\s+solidity|contract\s+\w+|library\s+\w+|interface\s+\w+|import|function\s+\w+|struct\s+\w+|enum\s+\w+|error\s+\w+|type\s+\w+)\b",
        mask_source(text),
    ):
        raise UploadError("File does not contain recognizable Solidity source")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def prepare_upload(stream: IO[bytes], filename: str, temp_root: Path, policy: UploadPolicy) -> Path:
    """Copy a bounded source into a unique directory; callers own cleanup."""
    suffix = Path(filename).suffix.lower()
    if any(char in filename for char in "/\\:\x00") or len(filename) > 150:
        raise UploadError("Upload filename must be a plain basename")
    if suffix not in {".sol", ".zip"}:
        raise UploadError("Upload a .sol file or .zip source project")
    data = stream.read(policy.max_upload + 1)
    if len(data) > policy.max_upload:
        raise UploadError("Upload exceeds the size limit")
    temp_root.mkdir(parents=True, exist_ok=True)
    root = temp_root / str(uuid.uuid4())
    root.mkdir(mode=0o700)
    try:
        if suffix == ".zip":
            extract_sources(data, root, policy)
        else:
            text = validate_source(data)
            (root / f"{uuid.uuid4().hex}.sol").write_text(text, encoding="utf-8", newline="\n")
        return root
    except BaseException:
        shutil.rmtree(root)
        raise


def archive_path(name: str) -> PurePosixPath:
    """Reject traversal, absolute paths, ambiguous Windows names, and excessive nesting."""
    if not name or len(name) > 240 or any(char in name for char in "\\:\x00"):
        raise UploadError("Unsafe archive filename")
    path = PurePosixPath(name)
    parts = name.rstrip("/").split("/")
    if path.is_absolute() or len(parts) > 10 or any(part in {"", ".", ".."} for part in parts):
        raise UploadError("Archive path traversal is not allowed")
    for part in parts:
        if part.endswith((".", " ")) or any(ord(char) < 32 for char in part):
            raise UploadError("Ambiguous archive filename")
        if re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part):
            raise UploadError("Reserved archive filename")
    return path


def extract_sources(data: bytes, root: Path, policy: UploadPolicy) -> None:
    """Extract Solidity-only ZIPs with streamed byte accounting and zip-slip protection."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > policy.max_files * 2:
                raise UploadError("Archive contains too many entries")
            seen: set[str] = set()
            total = count = 0
            for entry in entries:
                path = archive_path(entry.orig_filename)
                key = path.as_posix().casefold()
                if key in seen:
                    raise UploadError("Duplicate archive paths are not allowed")
                seen.add(key)
                mode = entry.external_attr >> 16
                if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}):
                    raise UploadError("Links and special files are not allowed")
                if entry.flag_bits & 1:
                    raise UploadError("Encrypted ZIPs are not supported")
                target = root.joinpath(*path.parts)
                if not target.resolve().is_relative_to(root.resolve()):
                    raise UploadError("Archive extraction escaped the source root")
                if entry.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if path.suffix != ".sol":
                    raise UploadError(
                        "ZIP projects may contain only .sol source files and directories"
                    )
                count += 1
                if count > policy.max_files or entry.file_size > policy.max_upload:
                    raise UploadError("Archive exceeds file count or per-file byte limit")
                if entry.file_size > policy.max_ratio * max(1, entry.compress_size):
                    raise UploadError("Archive compression ratio exceeds the limit")
                chunks = []
                size = 0
                with archive.open(entry) as stream:
                    while chunk := stream.read(64 * 1024):
                        size += len(chunk)
                        total += len(chunk)
                        if size > policy.max_upload or total > policy.max_extracted:
                            raise UploadError("Archive expanded size exceeds the limit")
                        chunks.append(chunk)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(validate_source(b"".join(chunks)), encoding="utf-8", newline="\n")
            if count == 0:
                raise UploadError("Archive contains no Solidity source")
    except (zipfile.BadZipFile, RuntimeError, OSError, NotImplementedError) as exc:
        raise UploadError("Invalid or unsupported ZIP archive") from exc


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
            with file.open("rb") as source_stream:
                data = source_stream.read(policy.max_upload + 1)
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
