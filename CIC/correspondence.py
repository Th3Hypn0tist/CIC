from __future__ import annotations

"""Read-only EXPECTED / DECLARED / OBSERVED evidence correspondence.

An exact marker can bind an observed source to a canonical identity, but
cannot prove implementation behavior matches the canonical contract.
Missing markers never trigger path/name guesses, including #FILE matching.
"""

import copy
from typing import Any


def compare_implementation_correspondence(
    expected_cw: dict[str, Any],
    imported_ir: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(expected_cw,dict) or not isinstance(expected_cw.get("entities"),list):
        raise ValueError("EXPECTED requires canonical CW entities")
    if not isinstance(imported_ir,dict) or not isinstance(imported_ir.get("files"),list):
        raise ValueError("OBSERVED requires imported CIC Code IR files")

    expected_by_id: dict[str,dict[str,Any]]={}
    for entity in expected_cw["entities"]:
        ref=entity.get("id") if isinstance(entity,dict) else None
        if not isinstance(ref,str) or not ref or ref in expected_by_id:
            raise ValueError("EXPECTED canonical Entity refs must be unique")
        expected_by_id[ref]=entity
    observed_by_path: dict[str,dict[str,Any]]={}
    for file in imported_ir["files"]:
        path=file.get("path") if isinstance(file,dict) else None
        if not isinstance(path,str) or not path or path in observed_by_path:
            raise ValueError("OBSERVED implementation paths must be unique")
        observed_by_path[path]=file

    markers=imported_ir.get("declared_marker_evidence",[])
    if not isinstance(markers,list):
        raise ValueError("DECLARED marker evidence must be an array")
    declarations_by_file: dict[str,list[dict[str,Any]]]={}
    for marker in markers:
        if not isinstance(marker,dict):continue
        path=marker.get("source_path")
        if not isinstance(path,str) or path not in observed_by_path:continue
        declarations_by_file.setdefault(path,[]).append(marker)

    # A single canonical marker may appear repeatedly within one file,
    # but declarations in distinct files are an identity-cloning conflict.
    marker_owners: dict[str,set[str]]={}
    for path,items in declarations_by_file.items():
        for item in items:
            if item.get("marker_type")=="FILE":
                ref=item.get("marker_ref")
                if isinstance(ref,str):
                    marker_owners.setdefault(ref,set()).add(path)
    cloned={ref:paths for ref,paths in marker_owners.items() if len(paths)>1}

    findings=[]
    claimed_expected=set()
    for path,file in sorted(observed_by_path.items()):
        declared=declarations_by_file.get(path,[])
        file_markers=[item for item in declared if item.get("marker_type")=="FILE"]
        refs={item.get("marker_ref") for item in file_markers
              if isinstance(item.get("marker_ref"),str)}
        if len(refs)>1:
            state="SEMANTIC_CONFLICT"
            note="One observed file declares multiple distinct #FILE bindings"
            identity_ref=None
        elif refs.intersection(cloned):
            state="SEMANTIC_CONFLICT"
            note="Exact #FILE marker is declared by multiple observed source files"
            identity_ref=next(iter(refs))
        elif len(refs)==0:
            state="UNRESOLVED"
            note="No exact #FILE declaration; observed path is not canonical authority"
            identity_ref=None
        else:
            identity_ref=next(iter(refs))
            if identity_ref not in expected_by_id:
                state="UNRESOLVED"
                note="Declared #FILE ref does not resolve in EXPECTED CW"
            else:
                claimed_expected.add(identity_ref)
                state="UNRESOLVED"
                note=("Exact identity declaration found; implementation semantics "
                      "still require deterministic comparison")
        findings.append({
            "state":state,
            "surface":"file",
            "canonical_binding_ref":identity_ref,
            "expected":(
                {"entity_ref":identity_ref,
                 "entity_type_ref":expected_by_id[identity_ref].get("entity_type_ref")}
                if identity_ref in expected_by_id else None
            ),
            "declared":[copy.deepcopy(marker) for marker in declared],
            "observed":{
                "file_ref":file.get("file_ref"),
                "source_path":path,
                "language_id":file.get("language_ir",{}).get("language_id")
                    if isinstance(file.get("language_ir"),dict) else None,
                "parser_evidence_available":isinstance(file.get("language_ir"),dict),
            },
            "identity_binding_proven":(
                len(refs)==1 and identity_ref in expected_by_id
                and identity_ref not in cloned
            ),
            "semantic_equivalence_proven":False,
            "reason":note,
        })

    for ref,entity in sorted(expected_by_id.items()):
        if not ref.startswith("#FILE:") or ref in claimed_expected:continue
        findings.append({
            "state":"UNRESOLVED","surface":"expected_file",
            "canonical_binding_ref":ref,
            "expected":{"entity_ref":ref,"entity_type_ref":entity.get("entity_type_ref")},
            "declared":[],"observed":None,
            "identity_binding_proven":False,"semantic_equivalence_proven":False,
            "reason":"No exact implemented binding proves this EXPECTED identity",
        })

    from collections import Counter
    states=dict(sorted(Counter(x["state"] for x in findings).items()))
    return {
        "kind":"cic_implementation_correspondence",
        "version":"1.0.0","canonical_semantic_authority":False,
        "expected_source":"explicit CW argument",
        "declared_source":"CIC declared_marker_evidence",
        "observed_source":"CIC Code IR files",
        "verdict":"UNRESOLVED",
        "reason":"Semantic equivalence requires surface-specific proven correspondence",
        "summary":states,
        "findings":findings,
        "mutated_inputs":False,
    }
