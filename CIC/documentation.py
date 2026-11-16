from __future__ import annotations

"""Deterministic Documentation evidence for the CIC Solver input.

Only source locations and *literal* canonical identity markers are extracted.
Prose, headings and lexical similarity do not establish canonical semantics.
This is an evidence surface, not a CW Entity or validation authority.
"""

import hashlib
import re
from pathlib import PurePosixPath
from typing import Any, Iterable

from CIC.identity import normalize_source_path


_DOCUMENT_SUFFIXES = frozenset({".md", ".markdown", ".rst", ".txt"})
# Exact marker grammar from Structure Implementation Correspondence Contract.
# The host-language comment or Markdown wrapper carries no additional meaning.
_MARKER_TYPES = (
    "FILE", "EVENT", "INTERFACE", "PROPERTY", "SCHEMA", "EFFECT",
    "CONSTRAINT", "REF", "CW", "CWREV", "CWEXPORT", "TARGET",
)
_MARKER_RE = re.compile(
    r"(?<![A-Za-z0-9_])#(?P<type>" + "|".join(_MARKER_TYPES)
    + r"):(?P<identity>[^\s<>\x00-\x1f,;\)\]\}\"'\u0060]+)"
)
_HEADING_RE = re.compile(r"^\s{0,3}(?:#{1,6}\s+|[=~-]{3,}\s*$)")


def extract_documentation_fragments(
    files: Iterable[dict[str, Any]], *, max_lines_per_fragment: int = 60,
) -> list[dict[str, Any]]:
    """Preserve doc prose with exact source spans, without semantic alignment.

    Document input is a subset of the *same imported source corpus*. Each
    fragment has a stable source-derived identity and one or more exact marker
    declarations. No ref is promoted to a canonical identity by this step.
    """
    if not isinstance(max_lines_per_fragment, int) or not 1 <= max_lines_per_fragment <= 1000:
        raise ValueError("max_lines_per_fragment must be 1..1000")
    result: list[dict[str, Any]] = []
    for file in files:
        if not isinstance(file, dict):
            raise TypeError("Documentation source entry must be an object")
        path = normalize_source_path(file.get("path"))
        content = file.get("content")
        if not isinstance(content, str):
            raise TypeError(f"Documentation content must be text: {path}")
        if PurePosixPath(path).suffix.lower() not in _DOCUMENT_SUFFIXES:
            continue
        lines = content.splitlines()
        start: int | None = None
        buffer: list[str] = []

        def emit() -> None:
            nonlocal start, buffer
            if start is None or not buffer:
                start = None
                buffer = []
                return
            text = "\n".join(buffer)
            markers: list[dict[str, str]] = []
            seen: set[str] = set()
            for match in _MARKER_RE.finditer(text):
                ref = "#" + match.group("type") + ":" + match.group("identity")
                if ref in seen:
                    continue
                seen.add(ref)
                markers.append({
                    "ref": ref, "marker_type": match.group("type"),
                    "authority": "declared_marker_only",
                })
            digest = hashlib.sha256(
                f"{path}\x00{start}\x00{text}".encode("utf-8")
            ).hexdigest()[:24]
            result.append({
                "fragment_ref": f"DOC::{path}::{start}:{digest}",
                "source_path": path,
                "source_span": {
                    "line": start,
                    "end_line": start + len(buffer) - 1,
                },
                "text": text,
                "markers": markers,
                "evidence_kind": "documentation",
                "canonical_semantic_authority": False,
            })
            start = None
            buffer = []

        for number, line in enumerate(lines, start=1):
            if not line.strip():
                emit()
                continue
            if buffer and (
                len(buffer) >= max_lines_per_fragment
                or (_HEADING_RE.match(line) and not _HEADING_RE.match(buffer[-1]))
            ):
                emit()
            if start is None:
                start = number
            buffer.append(line)
        emit()
    return result
