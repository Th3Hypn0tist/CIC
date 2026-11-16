from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable, Literal


SolverMode = Literal["off", "manual"]


@dataclass(frozen=True)
class SolverPolicy:
    """Explicit policy for the expensive semantic solver branch.

    The solver is OFF by default. `manual` mode requires an explicit positive
    token budget so a future bot-backed implementation cannot be entered by
    accident or by an unresolved parser observation alone.
    """

    mode: SolverMode = "off"
    token_budget: int = 0

    def __post_init__(self) -> None:
        if self.mode not in {"off", "manual"}:
            raise ValueError(f"unsupported CIC solver mode: {self.mode!r}")
        if not isinstance(self.token_budget, int) or self.token_budget < 0:
            raise ValueError("CIC solver token_budget must be a non-negative integer")
        if self.mode == "off" and self.token_budget != 0:
            raise ValueError("CIC solver OFF mode must have token_budget=0")
        if self.mode == "manual" and self.token_budget <= 0:
            raise ValueError("CIC solver manual mode requires an explicit positive token_budget")


@dataclass(frozen=True)
class SolverResult:
    """Non-authoritative evidence preparation; no canonical effects."""

    ir: dict[str, Any]
    status: str
    mode: SolverMode
    token_budget: int
    tokens_used: int
    proposals: tuple[dict[str, Any], ...]
    canonical_changes: int
    placeholder: bool
    provider_ref: str | None = None

    def report(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "mode": self.mode,
            "token_budget": self.token_budget,
            "tokens_used": self.tokens_used,
            "proposal_count": len(self.proposals),
            "canonical_changes": self.canonical_changes,
            "placeholder": self.placeholder,
            "provider_ref": self.provider_ref,
            "provider_connected": self.provider_ref is not None,
        }


def _evidence_alignment_proposals(ir: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    """Produce explicit, non-authoritative candidates for human/bot review.

    Only literal marker equality may nominate an observed implementation
    identity. A marker is a DECLARED claim; it never proves OBSERVED behavior
    satisfies canonical EXPECTED semantics.
    """
    imported: dict[str, list[dict[str, Any]]] = {}
    for file in ir.get("files", []):
        if not isinstance(file, dict):
            continue
        canonical = file.get("canonical_file_ref")
        if isinstance(canonical, str) and canonical:
            imported.setdefault(canonical, []).append(file)

    proposals: list[dict[str, Any]] = []
    for fragment in ir.get("documentation_evidence", []):
        if not isinstance(fragment, dict):
            continue
        fragment_ref = fragment.get("fragment_ref")
        location = fragment.get("source_span")
        for marker in fragment.get("markers", []):
            if not isinstance(marker, dict):
                continue
            marker_ref = marker.get("ref")
            if not isinstance(marker_ref, str) or not marker_ref:
                continue
            # Other marker kinds cannot be matched to observed FILE
            # evidence; leave them unresolved for a future exact-binding
            # correspondence stage, never guess function/property owners.
            matches = imported.get(marker_ref, []) if marker.get("marker_type") == "FILE" else []
            state = "proposed" if len(matches) == 1 else "unresolved"
            reasons = (
                ["EXACT_FILE_MARKER_DECLARED_NOT_OBSERVED_SEMANTICS"]
                if state == "proposed"
                else ["NO_UNIQUE_IMPLEMENTATION_EVIDENCE"]
            )
            proposals.append({
                "proposal_ref": f"{fragment_ref}::{marker_ref}",
                "state": state,
                "claim_kind": "documentation_implementation_alignment",
                "declared_marker_ref": marker_ref,
                "documentation_fragment_ref": fragment_ref,
                "documentation_location": location,
                "implementation_evidence_refs": [
                    match["file_ref"] for match in matches
                ],
                "observed_source_paths": [
                    match["path"] for match in matches
                ],
                "reasons": reasons,
                "canonical_claim": None,
                "canonical_changes": 0,
                "semantic_match_verified": False,
            })
    return tuple(proposals)


def run_solver(
    ir: dict[str, Any],
    *,
    policy: SolverPolicy | None = None,
    proposal_provider: Callable[[dict[str, Any], int], dict[str, Any]] | None = None,
    provider_ref: str | None = None,
) -> SolverResult:
    """Run the CIC solver branch without changing semantics.

    OFF remains zero-cost pass-through. MANUAL uses exact documentation
    marker references to prepare non-authoritative correspondence candidates.
    It does not make semantic claims, consume tokens, execute a bot or
    change canonical CW. Unmatched markers stay explicitly unresolved.

    A future token-backed implementation must keep solver output as proposals
    only. Proposal validation/application remains a separate deterministic
    boundary before anything can affect canonical CW.
    """
    if not isinstance(ir, dict):
        raise TypeError("CIC solver input must be a Code IR object")

    selected = policy or SolverPolicy()
    if proposal_provider is not None and selected.mode != "manual":
        raise ValueError("Solver provider requires explicit manual mode")
    if proposal_provider is not None and (
        not callable(proposal_provider)
        or not isinstance(provider_ref, str) or not provider_ref.strip()
    ):
        raise ValueError("Solver provider requires callable and explicit provider_ref")
    if proposal_provider is None and provider_ref is not None:
        raise ValueError("provider_ref cannot imply a connected bot")

    prepared = _evidence_alignment_proposals(ir) if selected.mode == "manual" else ()
    tokens_used = 0
    provider_proposals: tuple[dict[str, Any], ...] = ()
    if proposal_provider is not None:
        # The provider receives a detached copy of implementation +
        # documentation evidence, never an editable CW authority object.
        response = proposal_provider(copy.deepcopy(ir), selected.token_budget)
        if not isinstance(response, dict):
            raise ValueError("Solver provider response must be an object")
        usage = response.get("tokens_used")
        records = response.get("proposals")
        if not isinstance(usage, int) or isinstance(usage, bool) or not (
            0 <= usage <= selected.token_budget
        ):
            raise ValueError("Solver provider exceeded or omitted token budget")
        if not isinstance(records, list):
            raise ValueError("Solver provider proposals must be an array")
        known_evidence = {
            record.get("fragment_ref")
            for record in ir.get("documentation_evidence", [])
            if isinstance(record, dict)
        } | {
            record.get("file_ref")
            for record in ir.get("files", [])
            if isinstance(record, dict)
        } | {
            record.get("call_id")
            for record in ir.get("call_evidence", [])
            if isinstance(record, dict)
        } | {
            record.get("evidence_ref")
            for record in ir.get("declared_marker_evidence", [])
            if isinstance(record, dict)
        } | {
            record.get("evidence_id")
            for record in ir.get("reference_evidence", [])
            if isinstance(record, dict)
        }
        known_evidence.discard(None)
        seen_refs: set[str] = set()
        validated: list[dict[str, Any]] = []
        for record in records:
            if not isinstance(record, dict):
                raise ValueError("Solver proposal must be an object")
            ref = record.get("proposal_ref")
            evidence_refs = record.get("evidence_refs")
            if not isinstance(ref, str) or not ref or ref in seen_refs:
                raise ValueError("Solver proposal identity missing or duplicated")
            if (not isinstance(evidence_refs, list) or not evidence_refs
                or not all(isinstance(item, str)
                           and item in known_evidence for item in evidence_refs)):
                raise ValueError("Solver proposal lacks exact known evidence")
            if record.get("canonical_changes") not in (None, 0):
                raise ValueError("Solver may not claim canonical mutations")
            if record.get("state") not in (None, "proposed", "unresolved"):
                raise ValueError("Solver may produce proposals, never approvals")
            if record.get("canonical_semantic_authority") is True:
                raise ValueError("Solver cannot declare canonical authority")
            seen_refs.add(ref)
            validated.append({
                **copy.deepcopy(record),
                "proposal_ref": ref,
                "evidence_refs": list(evidence_refs),
                "state": record.get("state") or "proposed",
                "canonical_changes": 0,
                "canonical_semantic_authority": False,
                "provider_ref": provider_ref,
            })
        tokens_used = usage
        provider_proposals = tuple(validated)

    status = (
        "PASS_THROUGH_DISABLED" if selected.mode == "off"
        else "PROVIDER_PROPOSALS_UNAPPROVED" if proposal_provider is not None
        else "EVIDENCE_PROPOSALS_ONLY"
    )
    return SolverResult(
        ir=ir,
        status=status,
        mode=selected.mode,
        token_budget=selected.token_budget,
        tokens_used=tokens_used,
        proposals=(*prepared, *provider_proposals),
        canonical_changes=0,
        placeholder=proposal_provider is None,
        provider_ref=provider_ref if proposal_provider is not None else None,
    )
