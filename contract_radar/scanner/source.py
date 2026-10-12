"""Offset-preserving Solidity lexical masking and source context."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def mask_source(text: str, *, strings: bool = True) -> str:
    """Blank comments and optionally strings, preserving all offsets/newlines."""
    out = list(text)
    i = 0
    while i < len(text):
        end = i
        if text.startswith("//", i):
            end = text.find("\n", i)
            if end == -1:
                end = len(text)
        elif text.startswith("/*", i):
            close = text.find("*/", i + 2)
            end = len(text) if close == -1 else close + 2
        elif text[i] in "\"'":
            quote = text[i]
            end = i + 1
            while end < len(text):
                if text[end] == "\\":
                    end += 2
                elif text[end] == quote:
                    end += 1
                    break
                else:
                    end += 1
            end = min(end, len(text))
            if not strings:
                i = end
                continue
        if end > i:
            for j in range(i, end):
                if out[j] not in "\r\n":
                    out[j] = " "
            i = end
        else:
            i += 1
    return "".join(out)


@dataclass(frozen=True)
class Source:
    """A relative source path and original UTF-8 text."""

    file: str
    text: str

    @property
    def masked(self) -> str:
        """Return analysis-safe source text."""
        return mask_source(self.text)

    @property
    def sloc(self) -> int:
        """Count lines with lexical code, retaining string-only statements."""
        return sum(
            bool(line.strip()) for line in mask_source(self.text, strings=False).splitlines()
        )

    def context(self, start: int, end: int) -> tuple[str, int]:
        """Return bounded context around a source range."""
        lines = self.text.splitlines()
        first = max(1, start - 2)
        last = min(len(lines), end + 2, first + 18)
        return "\n".join(line[:500] for line in lines[first - 1 : last]), first


def load_sources(root: Path) -> dict[str, Source]:
    """Load Solidity sources from an already validated source root."""
    return {
        path.relative_to(root).as_posix(): Source(
            path.relative_to(root).as_posix(), path.read_text(encoding="utf-8-sig")
        )
        for path in sorted(root.rglob("*.sol"))
    }
