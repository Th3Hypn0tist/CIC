from __future__ import annotations

"""Derived implementation StructureTree from the existing CIC Code IR.

Each source file remains one observed FILE node, with Function/method
primitives as scoped surfaces. Calls and imports are distinct evidence records.
No observed identity is promoted to canonical CW, no semantic relation is
guessed, and no source code is executed.
"""

import copy
from collections import Counter
from typing import Any


def _function_records(symbol: dict[str, Any]):
    kind = symbol.get("kind")
    if kind == "function":
        yield symbol
    elif kind == "class":
        for method in symbol.get("methods", []):
            if isinstance(method, dict):
                yield from _function_records({**method,"kind":"function"})
    for child in symbol.get("nested_functions", []):
        if isinstance(child, dict):
            yield from _function_records(child)


def build_observed_structuretree(ir: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(ir, dict) or not isinstance(ir.get("files"), list):
        raise ValueError("Observed StructureTree needs CIC Code IR files")
    items: list[dict[str, Any]] = []
    seen_refs: set[str] = set()
    warnings: list[dict[str, Any]] = []

    def add(ref: str, surface: str, semantic: dict[str, Any],
            evidence_ref: str) -> None:
        if not isinstance(ref, str) or not ref or ref in seen_refs:
            raise ValueError("Duplicate or invalid observed evidence identity: "+str(ref))
        seen_refs.add(ref)
        items.append({
            "ref": ref,
            "surface": surface,
            "semantic": copy.deepcopy(semantic),
            "evidence_ref": evidence_ref,
            "canonical_semantic_authority": False,
        })

    for file in ir["files"]:
        if not isinstance(file, dict):
            raise ValueError("Invalid CIC file evidence")
        path = file.get("path")
        file_ref = file.get("file_ref")
        language_ir = file.get("language_ir")
        if not isinstance(path, str) or not isinstance(file_ref, str):
            raise ValueError("CIC observed FILE identity missing")
        if not isinstance(language_ir, dict):
            raise ValueError("CIC language evidence missing")
        language_id = language_ir.get("language_id")
        add(file_ref, "entity", {
            "kind": "observed_source_file",
            "source_path": path,
            "language_id": language_id,
        }, file_ref)
        if language_ir.get("diagnostics"):
            warnings.append({
                "source_path": path,
                "kind": "parser_diagnostics_present",
                "count": len(language_ir["diagnostics"]),
            })
        if language_ir.get("parser_available") is False:
            warnings.append({
                "source_path": path,
                "kind": "parser_unavailable",
            })

        # Function surfaces are evidence nested within one observed FILE.
        # They do not create additional FILE Entity identities.
        function_refs: set[str] = set()
        for symbol in language_ir.get("symbols", []):
            if not isinstance(symbol, dict):
                continue
            for function in _function_records(symbol):
                qualified = function.get("qualified_name")
                if not isinstance(qualified, str) or not qualified:
                    warnings.append({
                        "source_path": path,
                        "kind": "unqualified_function_evidence",
                    })
                    continue
                ref = "OBS_FUNCTION::"+file_ref+"::"+qualified
                if ref in function_refs:
                    raise ValueError("Duplicate observed Function: "+ref)
                function_refs.add(ref)
                primitive = function.get("primitive_decomposition")
                if not isinstance(primitive, dict):
                    primitive = {}
                add(ref, "function", {
                    "kind": "observed_function",
                    "qualified_name": qualified,
                    "parameters": copy.deepcopy(function.get("parameters", [])),
                    "returns_annotation": function.get("returns_annotation"),
                    "async": function.get("async"),
                    "decomposition_state": function.get(
                        "decomposition_state", "none",
                    ),
                }, ref)
                if primitive:
                    add("OBS_LOGIC::"+ref,"function_logic",{
                        "kind":"observed_primitive_logic",
                        "primitive_set_ref":primitive.get("primitive_set_ref"),
                        # Explicit ordered Function logic body: NEVER sort.
                        "body":copy.deepcopy(primitive.get("body",[])),
                        "unresolved":copy.deepcopy(primitive.get("unresolved",[])),
                        "decomposition_state":primitive.get("decomposition_state"),
                    }, ref)
        # Import evidence uses per-record identity (no endpoint coalescing).
        for index, record in enumerate(language_ir.get("imports", [])):
            if not isinstance(record, dict):
                continue
            ref="OBS_IMPORT::"+file_ref+"::"+str(index)
            add(ref, "import", {
                "source_file_ref": file_ref,
                "kind": record.get("kind"),
                "module": record.get("module"),
                "names": copy.deepcopy(record.get("names",[])),
                "level": record.get("level"),
                "alias": record.get("alias"),
            }, ref)

    # Call-site identity is never just (caller, callee): repeated invocations
    # and distinct source locations remain separate implementation evidence.
    for record in ir.get("call_evidence", []):
        if not isinstance(record, dict):
            continue
        ref=record.get("call_id")
        if not isinstance(ref,str) or not ref:
            warnings.append({"kind":"call_site_identity_missing"})
            continue
        add(ref,"call_site",{
            "source_function_ref":record.get("source_function_ref"),
            "target_function_ref":record.get("target_function_ref"),
            "target_expression":record.get("target_expression"),
            "resolution_status":record.get("resolution_status"),
            "source_line":record.get("line"),
            "call":copy.deepcopy(record.get("cic_ir",{})),
        },ref)

    counts=dict(sorted(Counter(item["surface"] for item in items).items()))
    return {
        "kind": "cic_observed_structuretree",
        "version": "1.0.0",
        "items": items,
        # Only inventory of imported text source FILEs is exhaustive here.
        # Language parser coverage, Function completeness and implicit call
        # behavior cannot be declared complete without separate evidence.
        "complete_surfaces": ["entity"],
        "summary": counts,
        "warnings": warnings,
        "canonical_semantic_authority": False,
        "source_kind": "deterministic_CIC_Code_IR",
        "one_source_file_one_observed_FILE_identity": True,
        "function_surfaces_are_not_FILE_entities": True,
        "source_executed": False,
    }
