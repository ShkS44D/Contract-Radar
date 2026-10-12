"""Deadline-bound subprocesses with bounded output and child cleanup."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


class ProcessTimeout(TimeoutError):
    """The process group exceeded its deadline."""


class OutputLimitError(RuntimeError):
    """The process emitted more diagnostics than permitted."""


@dataclass(frozen=True)
class ProcessResult:
    """Bounded process output and return code."""

    returncode: int
    stdout: str
    stderr: str


def terminate_tree(process: subprocess.Popen[bytes]) -> None:
    """Terminate the entire scan process tree on supported platforms."""
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()
    process.wait(timeout=10)


def run_process(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: float,
    output_limit: int = 2_000_000,
) -> ProcessResult:
    """Run an argument list without a shell, killing children on deadline/output overflow."""
    if sys.platform == "win32":
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        creation_flags = 0
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(
            args,
            cwd=cwd,
            env=env,
            stdout=stdout,
            stderr=stderr,
            start_new_session=os.name != "nt",
            creationflags=creation_flags,
        )
        deadline = time.monotonic() + timeout
        try:
            while process.poll() is None:
                if time.monotonic() >= deadline:
                    raise ProcessTimeout(f"Process exceeded {timeout:.1f}s deadline")
                if (
                    os.fstat(stdout.fileno()).st_size + os.fstat(stderr.fileno()).st_size
                    > output_limit
                ):
                    raise OutputLimitError("Scanner diagnostic output exceeded limit")
                time.sleep(0.05)
            if os.fstat(stdout.fileno()).st_size + os.fstat(stderr.fileno()).st_size > output_limit:
                raise OutputLimitError("Scanner diagnostic output exceeded limit")
        except BaseException:
            terminate_tree(process)
            raise
        stdout.seek(0)
        stderr.seek(0)
        return ProcessResult(
            process.returncode,
            stdout.read(output_limit).decode("utf-8", errors="replace"),
            stderr.read(output_limit).decode("utf-8", errors="replace"),
        )
