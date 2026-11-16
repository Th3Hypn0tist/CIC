from __future__ import annotations

"""Read-only normalized StructureTree semantic comparison.

This consumes two *already derived* StructureTree evidence envelopes, never raw
source paths or renderer geometry. Every cross-tree binding must carry explicit
approved evidence or exact generation provenance. Neither lexical similarity
nor equality of generated projection ids establishes correspondence.

A declared comparison context may cover a subset of semantic surfaces; an
EQUIVALENT verdict is always scoped to exactly that declared, complete context.
The caller remains responsible for establishing that the envelopes accurately
represent their source evidence and that a context covers the required model.
"""

import copy
import json
from collections import Counter
from typing import Any

_SURFACES = frozenset({
    "entity", "property", "function", "function_logic", "event",
    "event_handler", "call_site", "data_read", "data_write", "link",
    "dependency", "containment", "import", "topology_membership",
})
_ACCEPTED_BINDINGS = frozenset({
    "exact_generation_provenance", "approved_correspondence",
    "exact_canonical_marker",
})
# The structural fields below are transport only; all semantic data belongs
# inside item.semantic and is compared recursively, including array order.
_VIEW_FIELDS = frozenset({
    "position", "camera", "selection", "render_id",
    "projection_id", "transient_id", "view_state", "geometry",
})


def _index(tree: dict[str, Any], side: str) -> dict[str, dict[str, Any]]:
    items = tree.get("items")
    if not isinstance(items, list):
        raise ValueError(f"{side} StructureTree requires items[]")
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{side} StructureTree item must be an object")
        ref, surface, semantic = (
            item.get("ref"), item.get("surface"), item.get("semantic"),
        )
        if not isinstance(ref, str) or not ref or ref in result:
            raise ValueError(f"{side} item ref must be unique and nonempty")
        if surface not in _SURFACES or not isinstance(semantic, dict):
            raise ValueError(f"{side} item {ref} needs supported surface and semantic object")
        if set(semantic).intersection(_VIEW_FIELDS):
            raise ValueError(
                f"{side} semantic payload of {ref} contains renderer-only fields"
            )
        result[ref] = item
    return result


def _stable(value: Any) -> str:
    # Exact semantic object equality ignores key serialization order, but
    # preserves lists (Function body operations, call-site multiplicity, etc.).
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)


def compare_structuretrees(
    expected: dict[str, Any],
    observed: dict[str, Any],
    *,
    context: dict[str, Any],
    bindings: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare explicit semantic surfaces under a single declared context.

    Contract states: EQUIVALENT, IMPORT_ONLY, EXPORT_ONLY, MISMATCH,
    UNRESOLVED. No implicit many-to-one bindings. A report remains derived.
    """
    if not isinstance(expected, dict) or not isinstance(observed, dict):
        raise ValueError("Two derived StructureTree objects are required")
    if not isinstance(context, dict):
        raise ValueError("Explicit comparison context required")
    topology = context.get("topology_ref")
    abstraction = context.get("abstraction_level")
    surfaces = context.get("surfaces")
    if not isinstance(topology, str) or not topology:
        raise ValueError("Comparison context requires topology_ref")
    if not isinstance(abstraction, str) or not abstraction:
        raise ValueError("Comparison context requires abstraction_level")
    if not isinstance(surfaces, list) or not surfaces or any(
        surface not in _SURFACES for surface in surfaces
    ) or len(set(surfaces)) != len(surfaces):
        raise ValueError("Comparison context requires unique supported surfaces")
    if not isinstance(bindings, list):
        raise ValueError("Correspondence bindings must be a list")

    left = _index(expected, "EXPECTED")
    right = _index(observed, "OBSERVED")
    selected = set(surfaces)
    left_selected = {ref: item for ref, item in left.items()
                     if item["surface"] in selected}
    right_selected = {ref: item for ref, item in right.items()
                      if item["surface"] in selected}

    findings: list[dict[str, Any]] = []
    bound_left: set[str] = set()
    bound_right: set[str] = set()
    for binding in bindings:
        if not isinstance(binding, dict):
            raise ValueError("Each correspondence binding must be an object")
        a, b, authority = (
            binding.get("expected_ref"), binding.get("observed_ref"),
            binding.get("authority"),
        )
        evidence_ref = binding.get("evidence_ref")
        if (not isinstance(a, str) or not a or not isinstance(b, str)
                or not b or authority not in _ACCEPTED_BINDINGS
                or not isinstance(evidence_ref, str) or not evidence_ref):
            raise ValueError("Binding requires exact refs, authority and provenance")
        if a in bound_left or b in bound_right:
            raise ValueError("Many-to-one correspondence is forbidden")
        bound_left.add(a)
        bound_right.add(b)
        item_a, item_b = left_selected.get(a), right_selected.get(b)
        if item_a is None or item_b is None:
            findings.append({
                "state": "UNRESOLVED", "expected_ref": a, "observed_ref": b,
                "reason": "Binding does not resolve in selected comparison context",
                "evidence_ref": evidence_ref,
            })
            continue
        if item_a["surface"] != item_b["surface"]:
            findings.append({
                "state": "MISMATCH", "expected_ref": a, "observed_ref": b,
                "surface": item_a["surface"], "reason": "Different semantic surfaces",
                "evidence_ref": evidence_ref,
            })
            continue
        match = _stable(item_a["semantic"]) == _stable(item_b["semantic"])
        findings.append({
            "state": "EQUIVALENT" if match else "MISMATCH",
            "expected_ref": a, "observed_ref": b,
            "surface": item_a["surface"],
            "evidence_ref": evidence_ref, "binding_authority": authority,
            "reason": "Exact normalized semantic equality" if match
                else "Bound semantic payload differs",
            **({ "expected_semantic": copy.deepcopy(item_a["semantic"]),
                 "observed_semantic": copy.deepcopy(item_b["semantic"])}
               if not match else {}),
        })

    for ref, item in left_selected.items():
        if ref not in bound_left:
            findings.append({
                "state": "EXPORT_ONLY", "surface": item["surface"],
                "expected_ref": ref, "observed_ref": None,
                "reason": "No explicitly bound observed counterpart",
            })
    for ref, item in right_selected.items():
        if ref not in bound_right:
            findings.append({
                "state": "IMPORT_ONLY", "surface": item["surface"],
                "expected_ref": None, "observed_ref": ref,
                "reason": "No explicitly bound canonical counterpart",
            })

    # Completeness is a source assertion, not a comparator inference. Both
    # evidence producers must declare exhaustive coverage of every selected
    # semantic surface; otherwise EQUIVALENT cannot be proven.
    left_coverage = set(expected.get("complete_surfaces", []))
    right_coverage = set(observed.get("complete_surfaces", []))
    missing_coverage = sorted(
        (selected-left_coverage) | (selected-right_coverage)
    )
    if missing_coverage:
        findings.append({
            "state": "UNRESOLVED", "surface": "coverage",
            "reason": "Required comparison surface is not exhaustively represented",
            "missing_complete_surfaces": missing_coverage,
        })
    if not left_selected and not right_selected:
        findings.append({
            "state": "UNRESOLVED", "surface": "scope",
            "reason": "No semantic items to establish correspondence",
        })

    counts = Counter(item["state"] for item in findings)
    if counts["MISMATCH"]:
        verdict = "MISMATCH"
    elif counts["UNRESOLVED"]:
        verdict = "UNRESOLVED"
    elif counts["IMPORT_ONLY"] and counts["EXPORT_ONLY"]:
        verdict = "UNRESOLVED"
    elif counts["IMPORT_ONLY"]:
        verdict = "IMPORT_ONLY"
    elif counts["EXPORT_ONLY"]:
        verdict = "EXPORT_ONLY"
    else:
        verdict = "EQUIVALENT"
    return {
        "kind": "cic_structuretree_comparison",
        "version": "1.0.0",
        "verdict": verdict,
        "context": copy.deepcopy(context),
        "summary": dict(sorted(counts.items())),
        "findings": findings,
        "canonical_semantic_authority": False,
        "mutated_inputs": False,
        "exhaustive_for_declared_context": not missing_coverage,
        "scope_is_global": False,
        "note": "Verdict applies only to the supplied explicit semantic context",
    }
