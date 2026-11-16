from __future__ import annotations

"""Exact-marker FILE inventory comparison, never full implementation verdict.

EXPECTED canonical FILE source metadata and OBSERVED lexical file inventory
may be compared only after an exact, unambiguous #FILE comment declaration.
A matching FILE inventory cannot prove Function, Link or runtime equivalence.
"""

from typing import Any

from CIC.canonical_structuretree import build_canonical_structuretree
from CIC.observed_structuretree import build_observed_structuretree
from CIC.structuretree_comparison import compare_structuretrees


def compare_imported_file_inventory(
    expected_cw: dict[str, Any],
    observed_ir: dict[str, Any],
) -> dict[str, Any]:
    expected=build_canonical_structuretree(expected_cw)
    observed=build_observed_structuretree(observed_ir)
    canonical_refs={
        item["ref"] for item in expected["items"] if item["surface"]=="entity"
    }
    observed_by_path={
        item["semantic"]["source_path"]:item["ref"]
        for item in observed["items"] if item["surface"]=="entity"
    }
    declared: dict[str,set[str]]={}
    marker_evidence: dict[tuple[str,str],list[str]]={}
    for entry in observed_ir.get("declared_marker_evidence", []):
        if not isinstance(entry,dict) or entry.get("marker_type")!="FILE":
            continue
        path,ref,evidence=(
            entry.get("source_path"),entry.get("marker_ref"),
            entry.get("evidence_ref"),
        )
        if not isinstance(path,str) or not isinstance(ref,str) or not isinstance(evidence,str):
            continue
        if path not in observed_by_path:
            continue
        declared.setdefault(path,set()).add(ref)
        marker_evidence.setdefault((path,ref),[]).append(evidence)
    paths_by_ref: dict[str,set[str]]={}
    for path,refs in declared.items():
        for ref in refs:
            paths_by_ref.setdefault(ref,set()).add(path)

    bindings=[]
    conflicts=[]
    for path,refs in sorted(declared.items()):
        if len(refs)!=1:
            conflicts.append({
                "source_path":path,"reason":"Ambiguous multiple exact FILE markers",
                "declared_refs":sorted(refs),
            })
            continue
        ref=next(iter(refs))
        if len(paths_by_ref[ref])!=1:
            conflicts.append({
                "source_path":path,"reason":"Cloned canonical FILE identity",
                "declared_refs":[ref],
                "conflicting_sources":sorted(paths_by_ref[ref]),
            })
            continue
        if ref not in canonical_refs:
            conflicts.append({
                "source_path":path,"reason":"Exact marker does not resolve in EXPECTED",
                "declared_refs":[ref],
            })
            continue
        bindings.append({
            "expected_ref":ref,
            "observed_ref":observed_by_path[path],
            "authority":"exact_canonical_marker",
            "evidence_ref":sorted(marker_evidence[(path,ref)])[0],
        })

    comparison=compare_structuretrees(
        expected,observed,
        context={
            "topology_ref":"code_import_file_inventory",
            "abstraction_level":"file",
            "surfaces":["entity"],
        },
        bindings=bindings,
    )
    return {
        "kind":"cic_import_file_inventory_comparison",
        "version":"1.0.0",
        "file_inventory_verdict":(
            "UNRESOLVED" if conflicts else comparison["verdict"]
        ),
        "implementation_semantic_verdict":"UNRESOLVED",
        "reason":"File inventory equivalence does not prove Function, call, Link, Event or implementation semantics",
        "exact_binding_count":len(bindings),
        "conflicts":conflicts,
        "comparison":comparison,
        "canonical_semantic_authority":False,
        "mutated_inputs":False,
    }
