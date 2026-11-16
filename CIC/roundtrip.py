from __future__ import annotations

"""One import path for existing and generated implementation evidence.

Generated target artifacts are never promoted to canonical truth. A round trip
must use the same public Code Import function and a separate correspondence
comparison, not a generator-specific inference shortcut.
"""

from collections.abc import Iterable
from typing import Any

from CIC.api_core import import_files
from CIC.correspondence import compare_implementation_correspondence
from CIC.import_comparison import compare_imported_file_inventory
from CIC.solver import SolverPolicy


def roundtrip_generated_code(
    expected_cw: dict[str, Any],
    generated_files: Iterable[dict[str, Any]],
    *,
    solver_policy: SolverPolicy | None = None,
) -> dict[str, Any]:
    if not isinstance(expected_cw, dict) or not isinstance(expected_cw.get("entities"), list):
        raise ValueError("Round-trip EXPECTED must be an explicit canonical CW model")
    records = list(generated_files)
    if not records:
        raise ValueError("Round-trip requires generated source files")
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("content"), str):
            raise ValueError("Round-trip requires {path, content} source records")
    # This is intentionally the ordinary CIC Code Import API, without a
    # generator-specific parser, language workaround or alternate authority.
    bundle = import_files(
        records, solver_policy=solver_policy or SolverPolicy(),
        materialize_events=False,
    )
    comparison = compare_implementation_correspondence(expected_cw, bundle.ir)
    file_inventory = compare_imported_file_inventory(expected_cw, bundle.ir)
    stages = [
        {
            "id": "code_input",
            "status": "OBSERVED",
            "file_count": len(records),
            "canonical_semantic_authority": False,
        },
        {
            "id": "same_code_import",
            "status": "IMPORTED",
            "file_count": bundle.files_imported,
            "unresolved_parser_diagnostics": bundle.diagnostics,
            "canonical_semantic_authority": False,
        },
        {
            "id": "solver",
            "status": bundle.ir.get("solver",{}).get("status", "UNAVAILABLE"),
            "canonical_changes": 0,
            "canonical_semantic_authority": False,
        },
        {
            "id": "file_inventory_comparison",
            "status": file_inventory["file_inventory_verdict"],
            "canonical_semantic_authority": False,
        },
        {
            "id": "structuretree_comparison",
            "status": comparison["verdict"],
            "canonical_semantic_authority": False,
        },
    ]
    return {
        "kind": "cic_generation_roundtrip",
        "version": "1.0.0",
        "status": comparison["verdict"],
        "stages": stages,
        "comparison": comparison,
        "file_inventory_comparison": file_inventory,
        "import_diagnostics": bundle.ir.get("diagnostic_summary", {}),
        "code_ir": bundle.ir,
        "canonical_mutations": 0,
        "production_executed": False,
        "generated_code_semantic_authority": False,
    }
