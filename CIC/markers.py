from __future__ import annotations

"""Explicit comment-carried canonical markers; declarations, not authority.

No marker is invented from names/paths or string-literal content. Every
declaration records an observed source location and literal marker text.
"""

import io
import re
import tokenize
from html.parser import HTMLParser
from pathlib import PurePosixPath
from typing import Any, Iterable

from CIC.identity import normalize_source_path
from CIC.modules.javascript import _lex as lex_js
from CIC.modules.css import _tokenize as lex_css

_MARKER = re.compile(
    r"(?<![A-Za-z0-9_])#(?P<kind>"
    r"FILE|EVENT|INTERFACE|PROPERTY|SCHEMA|EFFECT|CONSTRAINT|REF"
    r"|CWREV|CWEXPORT|TARGET|CW"
    r"):(?P<identity>[^\s<>\x00-\x1f,;\)\]\}\"'\u0060]+)"
)
_JS_SUFFIXES = frozenset({".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"})
_DOC_SUFFIXES = frozenset({".md", ".markdown", ".rst", ".txt"})
_HTML_SUFFIXES = frozenset({".html", ".htm"})


class _HTMLMarkerComments(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.records: list[tuple[int,int,str,str]] = []

    def handle_comment(self, data: str) -> None:
        line,column = self.getpos()
        self.records.append((line,column,"<!--"+data+"-->","html_comment"))


def _comments(path: str, text: str) -> list[tuple[int,int,str,str]]:
    suffix = PurePosixPath(path).suffix.lower()
    if suffix == ".py":
        result: list[tuple[int,int,str,str]] = []
        try:
            for token in tokenize.generate_tokens(io.StringIO(text).readline):
                if token.type == tokenize.COMMENT:
                    result.append((
                        token.start[0],token.start[1],token.string,"python_comment",
                    ))
        except (tokenize.TokenError,IndentationError):
            # Partial code is allowed; never read strings as markers.
            pass
        return result
    if suffix in _HTML_SUFFIXES:
        parser = _HTMLMarkerComments()
        parser.feed(text)
        return parser.records
    if suffix in _JS_SUFFIXES:
        tokens,_diagnostics = lex_js(text)
        return [(item.line,item.column,item.value,"js_comment")
                for item in tokens if item.kind=="comment"]
    if suffix == ".css":
        tokens,_diagnostics = lex_css(text)
        return [(item.line,item.column,item.value,"css_comment")
                for item in tokens if item.kind=="comment"]
    return []


def _offset_position(line: int,column: int,text: str,offset: int) -> dict[str,int]:
    before=text[:offset]
    breaks=before.count("\n")
    return {
        "line":line+breaks,
        "column":column+len(before) if breaks==0
        else len(before.rsplit("\n",1)[-1]),
    }

def extract_declared_markers(
    files: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    declarations: list[dict[str, Any]] = []
    for file in files:
        if not isinstance(file,dict):raise TypeError("Marker source must be object")
        path = normalize_source_path(file.get("path"))
        content = file.get("content")
        if not isinstance(content,str):raise TypeError("Marker content must be text")
        if PurePosixPath(path).suffix.lower() in _DOC_SUFFIXES:continue
        for line,column,comment,comment_kind in _comments(path,content):
            for match in _MARKER.finditer(comment):
                ref = "#" + match.group("kind") + ":" + match.group("identity")
                position = _offset_position(
                    line,column,comment,match.start(),
                )
                declarations.append({
                    "evidence_ref": (
                        f"MARKER::{path}::{position['line']}:"
                        f"{position['column']}::{ref}"
                    ),
                    "marker_ref": ref,
                    "marker_type": match.group("kind"),
                    "source_path": path,
                    "span": position,
                    "host_transport": comment_kind,
                    "evidence_kind":"declared_marker",
                    "canonical_semantic_authority":False,
                    "implementation_verified":False,
                })
    return declarations
