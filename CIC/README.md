# CIC

`CW/tools/CIC/` is the authoritative CIC source.

All other CIC copies are synchronized consumers. Their synchronization mechanism is owned elsewhere and does not change CIC authority.

## Boundary

CIC owns deterministic source acquisition, parser/evidence extraction, unbound CW candidate generation, transactional create/update, and Node version stamping.

CIC does **not** own canonical specification semantics. The CW specification set and CW linter remain independent authorities in this repository.

The public import gate therefore runs this exact order:

```text
validate CIC + CW tooling
  -> validate selected immutable CW specification set
  -> import source to staged unbound CW
  -> compose / representation-validate CW
  -> bind specification only in a temporary validation projection
  -> semantic CW validation
  -> timestamp changed/new Nodes
  -> calculate MD5 with hash field present as ""
  -> write shards
  -> read back and reverse-verify hashes
  -> semantic CW validation again
  -> atomically expose target CW
```

`READY` and `UNREADY` are both valid model states for the version gate. `INVALID_MODEL`, invalid specification/tooling, representation failure, or hash failure aborts the transaction and creates no new authoritative version.

The written CIC output remains specification-unbound. Temporary validation binding is evaluation context only and is never silently persisted by CIC.

Source and output trees must be disjoint. CIC rejects the same directory, an output that contains the source, and an output located anywhere inside the source tree. This prevents a subsequent import from ingesting an earlier generated CW snapshot as source input.

## Node version

```text
id        = persistent canonical Node identity
timestamp = YYYYMMDDhhmmss chronological version order
hash      = lowercase MD5 version checksum
```

Hash generation:

```text
validate first
timestamp = current UTC time formatted YYYYMMDDhhmmss
hash = ""
MD5(deterministic direct Entity shard serialization)
hash = calculated digest
write
read back
hash = ""
recalculate MD5
compare
```

An unchanged Node preserves its previous timestamp/hash during `--force` update. Only changed or new Nodes receive a new version.

MD5 is a fast version checksum. It is not security, authenticity, trust, or semantic identity authority.

## Local release gate

From the CW repository root:

```bash
python -m tools.CIC release-check
```

This is the authoritative local pre-sync gate. It:

1. compiles the CIC and CW validation tools,
2. validates the selected immutable specification closure,
3. runs the complete import -> semantic validation -> stamp -> reverse-verify selftest,
4. runs the CIC regression suite,
5. rejects `api_legacy.py`, `structuretree.py`, and imports of their old package paths.

The lower-level commands remain available:

```bash
python -m tools.CIC validate-tools
python -m tools.CIC selftest
python -m tools.CIC import <source-folder> <cw-folder>
python -m tools.CIC import <source-folder> <cw-folder> --force
```

The default validation context is the locked `spec_sets/CW_CORE_v1.1.0.json` bundle (CCF 2.4.3 / NodeTypes 1.18.0 / Rulesets 3.14.0). An explicit `--spec-set` may be supplied when intentionally evaluating another immutable bundle.

## Synchronization contract

`CW/tools/CIC/` is the source copied to consumer repositories. A synchronized consumer may expose it as top-level `CIC/`; the package bootstrap deliberately supports both locations without maintaining two implementations.

The public importer still requires access to the CW specification/linter authority. Inside the CW repository this is discovered automatically. When a synchronized CIC copy is executed from another repository, set `CW_ROOT` to a local CW checkout containing `spec_sets/` and `linter/`, or pass `cw_root` explicitly. A consumer copy must not carry or invent a parallel specification authority merely to make CIC self-contained.

The synchronization mechanism itself is outside CIC and outside this contract. A consumer copy does not become an authority merely because it is locally modified.

## SSOT rule

**One truth. Many topologies. No duplicate truth.**

For CIC itself, the one truth is this directory in the CW repository.


## Structure consumer: documentation and correspondence recovery

The synchronized `Structure/CIC/` consumer implements an additional,
**non-authoritative** evidence route while the application integration is
being restored. This does not transfer CIC source-of-truth status from the CW
repository to Structure.

The same `import_files` / `import_folder` importer now retains three
separate evidence surfaces:

- **EXPECTED:** a separately supplied canonical CW document.
- **DECLARED:** exact canonical markers observed in code comments, each with a
  source location; documentation fragments also retain literal markers.
- **OBSERVED:** deterministic parser, import, reference, call and event evidence.
  A marker alone never proves that observed implementation behavior matches
  EXPECTED semantics.

In the Structure consumer, `scan` and `import` expose explicit
`--solver-mode manual --solver-token-budget N` options. The default remains
`off`. Manual mode prepares inspectable exact-marker documentation
correspondence proposals. **It is not a connected bot-backed semantic solver**:
no tokens are spent, nothing is automatically approved, and no canonical
document is changed by these proposals.

The Structure consumer also exposes:

```bash
python -m CIC scan <source-folder>
python -m CIC scan <source-folder> --solver-mode manual --solver-token-budget 1000
python -m CIC correspondence <cw-input> <import.ir.json>
python -m CIC roundtrip <cw-input> <generated-files.json>
```

`generated-files.json` is a JSON list of `{"path":"...","content":"..."}`
records. Round-trip re-imports through **the same ordinary Code Import
path**, then produces a separate correspondence report. Until every required
semantic comparison surface has an exact proven binding and semantics
verification, the report remains `UNRESOLVED`; it must not be described as
equivalent merely because matching names or markers exist.

These are implementation-restoration changes in `deploy-cancidate`. They
have not yet passed the delayed conformance test phase.


## Explicit semantic StructureTree comparison

`compare-tree` is an additional *read-only* comparator for two already
materialized, evidence-backed semantic StructureTree envelopes. It does not
derive semantic bindings from filenames, labels or visual geometry.

```bash
python -m CIC compare-tree expected-tree.json observed-tree.json \
  context.json bindings.json
```

Each tree declares `items` with `ref`, `surface` and a structured
`semantic` object. Both trees declare `complete_surfaces`; incomplete
coverage prevents `EQUIVALENT`. Context declares `topology_ref`,
`abstraction_level` and a nonempty list of compared semantic surfaces.
Every cross-tree binding must declare `expected_ref`, `observed_ref`,
`authority` (`exact_generation_provenance`,
`approved_correspondence` or `exact_canonical_marker`) and the exact
`evidence_ref` supporting that binding.

Equality compares the supplied structured semantic payload, preserving
array order and distinct call-site records while ignoring JSON object key
serialization order. It **cannot** turn marker identity into a claim that
the implementation is behaviorally equivalent: source evidence extraction,
binding review, and comparison-context coverage remain separate. A verdict
of `EQUIVALENT` is scoped to the exact supplied surfaces and does **not**
claim global implementation equivalence.

The optional Solver proposal-provider port is available only through the
Python importer/scan APIs with an explicit manual `SolverPolicy`, a positive
budget and a named provider. The provider sees detached evidence and returns
inspectable unapproved proposals; imported CW is never changed by provider
output. No provider is registered by default, and CLI flags alone never
connect one.


## Canonical vs observed StructureTree views

The consumer's Code IR and CW-derived StructureTree are separately
materializable:

```bash
python -m CIC cw-tree <cw-input>
python -m CIC observed-tree <import.ir.json>
python -m CIC compare-import <cw-input> <import.ir.json>
```

`cw-tree` reads canonical `#FILE` Entities and their explicit source
metadata, plus attached Function/primitive surfaces. `observed-tree` reads
the existing Code IR: one observed FILE per source file, separate Function
surfaces, distinct call sites and import records. Both are **derived views**.

`compare-import` looks only at the **FILE inventory**, using a unique
literal `#FILE` declaration per observed file as an exact identity binding.
It can report `EQUIVALENT` for that narrowly defined FILE inventory context
only when canonical source metadata and the observed files agree with complete
coverage. Missing or cloned markers remain unresolved/conflicting. Its
independent `implementation_semantic_verdict` remains `UNRESOLVED`, because
matching files does not establish Function/call/flow/side-effect equivalence.

Likewise `roundtrip` now includes a separate FILE inventory comparison stage
without upgrading the full StructureTree comparison verdict.
