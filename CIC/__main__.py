from __future__ import annotations

import argparse
import ast
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from . import format_filetree, format_links, import_folder, ingest_cw, report_cw, scan_folder, validate_toolchain
from .cw_version import verify_cw_versions
from .report import format_cw_report
from .solver import SolverPolicy
from .correspondence import compare_implementation_correspondence
from .roundtrip import roundtrip_generated_code
from .structuretree_comparison import compare_structuretrees
from .observed_structuretree import build_observed_structuretree
from .canonical_structuretree import build_canonical_structuretree
from .import_comparison import compare_imported_file_inventory


def _selftest(cw_root=None, spec_set=None) -> dict:
    with tempfile.TemporaryDirectory(prefix="cw-cic-selftest-") as tmp:
        root = Path(tmp)
        source = root / "source"
        target = root / "model"
        source.mkdir()
        (source / "main.py").write_text(
            "def enabled(flag: bool):\n    if flag:\n        return True\n    return False\n",
            encoding="utf-8",
        )
        result = import_folder(source, target, cw_root=cw_root, spec_set=spec_set)
        document = ingest_cw(target)
        verify_cw_versions(document)
        versioned = [
            entity
            for entity in document.get("entities", [])
            if isinstance(entity, dict)
            and isinstance(entity.get("timestamp"), str)
            and isinstance(entity.get("hash"), str)
        ]
        if len(versioned) != len(document.get("entities", [])):
            raise RuntimeError("selftest produced unversioned Entity")
        if "specification_ref" in document:
            raise RuntimeError("CIC persisted temporary validation binding")
        return {
            "status": "PASS",
            "files_imported": result.files_imported,
            "shards": result.shard_count,
            "entities": len(document.get("entities", [])),
            "version_stamps": "verified",
            "specification_bound": False,
        }


def _forbidden_import_modules(path: Path) -> list[str]:
    forbidden = {"CIC.api_legacy", "CIC.structuretree"}
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        raise RuntimeError(f"cannot inspect CIC Python source {path}: {exc}") from exc

    hits: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for module in forbidden:
                    if alias.name == module or alias.name.startswith(module + "."):
                        hits.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and isinstance(node.module, str):
            for module in forbidden:
                if node.module == module or node.module.startswith(module + "."):
                    hits.add(node.module)
    return sorted(hits)


def _release_check(cw_root=None, spec_set=None) -> dict:
    root = Path(cw_root).expanduser().resolve() if cw_root else next(
        parent for parent in Path(__file__).resolve().parents if (parent / "spec_sets").is_dir() and (parent / "linter").is_dir()
    )
    cic_root = Path(__file__).resolve().parent

    forbidden_files = [path for path in (cic_root / "api_legacy.py", cic_root / "structuretree.py") if path.exists()]
    forbidden_imports: list[str] = []
    for path in cic_root.rglob("*.py"):
        for module in _forbidden_import_modules(path):
            forbidden_imports.append(f"{path.relative_to(cic_root)} -> {module}")
    if forbidden_files or forbidden_imports:
        raise RuntimeError(
            f"CIC release contains forbidden duplicate/domain remnants: files={forbidden_files}, imports={forbidden_imports}"
        )

    tool_report = validate_toolchain(cw_root=root, spec_set=spec_set)
    selftest_report = _selftest(root, spec_set)

    # The same regression suite must run from the CW SSOT location and from a
    # synchronized top-level CIC consumer. Propagate the resolved CW authority
    # for tests that intentionally call the public importer without cw_root.
    previous_cw_root = os.environ.get("CW_ROOT")
    os.environ["CW_ROOT"] = str(root)
    try:
        tools_path = str(root / "tools")
        if tools_path not in sys.path:
            sys.path.insert(0, tools_path)
        suite = unittest.defaultTestLoader.discover(str(cic_root / "tests"), pattern="test*.py")
        stream = io.StringIO()
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    finally:
        if previous_cw_root is None:
            os.environ.pop("CW_ROOT", None)
        else:
            os.environ["CW_ROOT"] = previous_cw_root

    if not result.wasSuccessful():
        raise RuntimeError("CIC regression suite failed:\n" + stream.getvalue())

    return {
        "status": "PASS",
        "toolchain": "validated",
        "selftest": selftest_report,
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "forbidden_files": 0,
        "forbidden_imports": 0,
        "specification_bound": False,
        "cw_root": str(root),
        "spec_report": tool_report,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.CIC")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("validate-tools")
    check.add_argument("--cw-root")
    check.add_argument("--spec-set")

    selftest = sub.add_parser("selftest")
    selftest.add_argument("--cw-root")
    selftest.add_argument("--spec-set")

    release_check = sub.add_parser("release-check")
    release_check.add_argument("--cw-root")
    release_check.add_argument("--spec-set")

    scan = sub.add_parser("scan")
    scan.add_argument("code_folder")
    scan.add_argument("--solver-mode",choices=("off","manual"),default="off")
    scan.add_argument("--solver-token-budget",type=int,default=0)

    imp = sub.add_parser("import")
    imp.add_argument("code_folder")
    imp.add_argument("cw_folder")
    imp.add_argument("--force", action="store_true")
    imp.add_argument("--cw-root")
    imp.add_argument("--spec-set")
    imp.add_argument("--solver-mode",choices=("off","manual"),default="off")
    imp.add_argument("--solver-token-budget",type=int,default=0)

    expected_tree = sub.add_parser("cw-tree")
    expected_tree.add_argument("cw_input")

    compare_import = sub.add_parser("compare-import")
    compare_import.add_argument("cw_input")
    compare_import.add_argument("import_ir")

    observed_tree = sub.add_parser("observed-tree")
    observed_tree.add_argument("import_ir")

    compare_tree = sub.add_parser("compare-tree")
    compare_tree.add_argument("expected_tree_json")
    compare_tree.add_argument("observed_tree_json")
    compare_tree.add_argument("context_json")
    compare_tree.add_argument("bindings_json")

    roundtrip = sub.add_parser("roundtrip")
    roundtrip.add_argument("cw_input")
    roundtrip.add_argument("generated_files_json")
    roundtrip.add_argument("--solver-mode",choices=("off","manual"),default="off")
    roundtrip.add_argument("--solver-token-budget",type=int,default=0)

    correspondence = sub.add_parser("correspondence")
    correspondence.add_argument("cw_input")
    correspondence.add_argument("import_ir")

    report = sub.add_parser("report")
    report.add_argument("cw_input")
    report.add_argument("--json", action="store_true", dest="as_json")

    test = sub.add_parser("test")
    test_sub = test.add_subparsers(dest="test_kind", required=True)
    for name in ("cw", "filetree", "links"):
        item = test_sub.add_parser(name)
        item.add_argument("cw_input")

    printer = sub.add_parser("print")
    print_sub = printer.add_subparsers(dest="print_kind", required=True)
    for name in ("filetree", "links"):
        item = print_sub.add_parser(name)
        item.add_argument("cw_input")

    args = parser.parse_args(argv)
    if args.command == "validate-tools":
        print(json.dumps({"status": "PASS", "report": validate_toolchain(cw_root=args.cw_root, spec_set=args.spec_set)}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "selftest":
        print(json.dumps(_selftest(args.cw_root, args.spec_set), ensure_ascii=False, indent=2))
        return 0
    if args.command == "release-check":
        print(json.dumps(_release_check(args.cw_root, args.spec_set), ensure_ascii=False, indent=2))
        return 0
    if args.command == "scan":
        policy=SolverPolicy(mode=args.solver_mode,token_budget=args.solver_token_budget)
        result = scan_folder(Path(args.code_folder),solver_policy=policy)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["cw_gate_b"]["status"] == "PASS" else 1
    if args.command == "import":
        policy=SolverPolicy(mode=args.solver_mode,token_budget=args.solver_token_budget)
        result = import_folder(Path(args.code_folder), Path(args.cw_folder),
                               force=args.force, cw_root=args.cw_root,
                               spec_set=args.spec_set, solver_policy=policy)
        print(json.dumps({
            "status": "OK",
            "code_folder": str(result.code_folder),
            "cw_folder": str(result.cw_folder),
            "cw_path": str(result.cw_path),
            "ir_path": str(result.ir_path),
            "shards": result.shard_count,
            "files_seen": result.files_seen,
            "files_imported": result.files_imported,
            "diagnostics": result.diagnostic_summary,
            "specification_bound": False,
            "version_stamped": True,
        }, ensure_ascii=False, indent=2))
        return 0
    if args.command == "cw-tree":
        canonical=ingest_cw(Path(args.cw_input))
        print(json.dumps(build_canonical_structuretree(canonical),
                         ensure_ascii=False,indent=2))
        return 0
    if args.command == "compare-import":
        canonical=ingest_cw(Path(args.cw_input))
        observed=json.loads(Path(args.import_ir).read_text(encoding="utf-8"))
        report=compare_imported_file_inventory(canonical,observed)
        print(json.dumps(report,ensure_ascii=False,indent=2))
        return 0 if report["file_inventory_verdict"]=="EQUIVALENT" else 2
    if args.command == "observed-tree":
        ir=json.loads(Path(args.import_ir).read_text(encoding="utf-8"))
        print(json.dumps(build_observed_structuretree(ir),
                         ensure_ascii=False,indent=2))
        return 0
    if args.command == "compare-tree":
        def load_json(path):
            return json.loads(Path(path).read_text(encoding="utf-8"))
        report=compare_structuretrees(
            load_json(args.expected_tree_json),
            load_json(args.observed_tree_json),
            context=load_json(args.context_json),
            bindings=load_json(args.bindings_json),
        )
        print(json.dumps(report,ensure_ascii=False,indent=2))
        return 0 if report["verdict"]=="EQUIVALENT" else 2
    if args.command == "roundtrip":
        expected=ingest_cw(Path(args.cw_input))
        generated=json.loads(Path(args.generated_files_json).read_text(encoding="utf-8"))
        policy=SolverPolicy(mode=args.solver_mode,token_budget=args.solver_token_budget)
        report=roundtrip_generated_code(expected,generated,solver_policy=policy)
        print(json.dumps(report,ensure_ascii=False,indent=2))
        return 0 if report["status"]=="EQUIVALENT" else 2
    if args.command == "correspondence":
        expected=ingest_cw(Path(args.cw_input))
        observed=json.loads(Path(args.import_ir).read_text(encoding="utf-8"))
        report=compare_implementation_correspondence(expected,observed)
        print(json.dumps(report,ensure_ascii=False,indent=2))
        return 0 if report["verdict"]=="MATCH" else 2
    if args.command == "report":
        result = report_cw(Path(args.cw_input))
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.as_json else format_cw_report(result))
        return 0 if result["verdict"] == "PASS" else 1
    if args.command == "test":
        document = ingest_cw(Path(args.cw_input))
        if args.test_kind == "filetree":
            format_filetree(document)
        elif args.test_kind == "links":
            format_links(document)
        print(json.dumps({"status": "PASS", "test": args.test_kind}))
        return 0
    if args.command == "print":
        document = ingest_cw(Path(args.cw_input))
        print(format_filetree(document) if args.print_kind == "filetree" else format_links(document))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
