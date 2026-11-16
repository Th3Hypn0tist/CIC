from __future__ import annotations

"""Explicit status of every contracted Structure canonicalization pipeline stage.

A stage without an implementation stays NOT_CONNECTED. A produced Code IR
is evidence; a CW candidate is not approved canonical truth.
"""

from typing import Any


def pipeline_status(ir: dict[str, Any], *, cw_candidate: bool) -> dict[str, Any]:
    if not isinstance(ir,dict):raise TypeError("Pipeline requires Code IR")
    solver=ir.get("solver") if isinstance(ir.get("solver"),dict) else {}
    files=ir.get("files") if isinstance(ir.get("files"),list) else []
    docs=ir.get("documentation_evidence") if isinstance(ir.get("documentation_evidence"),list) else []
    proposal_count=int(solver.get("proposal_count",0) or 0)
    mode=solver.get("mode","off")
    stages=[
        {"stage":"code","status":"OBSERVED","evidence_count":len(files)},
        {"stage":"code_import","status":"EVIDENCE_EXTRACTED",
         "evidence_count":len(files),
         "authority":"implementation_evidence"},
        {"stage":"documentation","status":"EVIDENCE_EXTRACTED",
         "evidence_count":len(docs),
         "authority":"documentation_evidence"},
        {"stage":"solver","status":(
            "OFF" if mode=="off"
            else "PROPOSALS_ONLY" if proposal_count else "NO_EVIDENCE_PROPOSALS"),
         "proposal_count":proposal_count,
         "bot_backed_semantic_alignment_connected":False,
         "canonical_mutations":0},
        {"stage":"cw_candidate",
         "status":"UNLOCKED_CANDIDATE" if cw_candidate else "NOT_MATERIALIZED",
         "authority":"not_validated_canonical_truth"},
        {"stage":"target_export","status":"NOT_CONNECTED",
         "detail":"No target adapter output supplied to CIC pipeline"},
        {"stage":"code_reimport","status":"NOT_CONNECTED",
         "detail":"No generated code supplied; use explicit roundtrip input"},
        {"stage":"structuretree_comparison","status":"NOT_CONNECTED",
         "detail":"Requires explicit EXPECTED and reimported OBSERVED evidence"},
    ]
    return {
        "kind":"structure_pipeline_stage_status",
        "version":"1.0.0",
        "stages":stages,
        "complete":False,
        "canonical_changes_from_solver":0,
        "silent_fallback":False,
    }
