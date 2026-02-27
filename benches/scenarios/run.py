#!/usr/bin/env python3
"""Runner for green-languages-scenarios benchmarks.

Discovers, extracts, compiles, and tests code scenarios from the
green-languages-scenarios repository. The agent edits source files
in-place in a workspace directory, then reruns build/test.

Usage:
    python3 run.py --dir ../green-languages-scenarios list
    python3 run.py --dir ../green-languages-scenarios prepare --workdir /tmp/scenarios
    python3 run.py --dir ../green-languages-scenarios compile --workdir /tmp/scenarios [SCENARIO]
    python3 run.py --dir ../green-languages-scenarios test --workdir /tmp/scenarios [SCENARIO]
    python3 run.py --dir ../green-languages-scenarios code SCENARIO
"""

import argparse
import os
import re
import shlex
import subprocess
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# -- Filtering --

MAX_YML_SIZE = 1_000_000  # Skip YAMLs > 1MB (huge expected_stdout blobs)
SKIP_DIRS = {"code"}  # code/ duplicates process/ with huge files
SKIP_LANGS = {"cs"}  # No .NET support
SKIP_CATEGORIES = {"sleepers"}  # Not useful for optimization
# Only keep English leetcode variants (danish/romanian are same code, different description)
SKIP_SUFFIXES = ("_danish", "_romanian")
# Known-failing scenarios (upstream issues)
SKIP_SCENARIOS = {
    "clbg/java/pidigits",  # Requires JDK 24+ preview APIs
    "leetcode/cpp/n-queens_english",  # Upstream expected_stdout whitespace mismatch
    "leetcode/ruby_cruby_3.4.3/n-queens_english",  # Same whitespace issue
}


@dataclass
class TestCase:
    args: list[str]
    expected_stdout: str | None  # None = skip verification


@dataclass
class Scenario:
    id: str  # e.g. "leetcode/cpp/n-queens_english"
    name: str  # e.g. "n-queens"
    lang: str  # normalized: c, cpp, java, python, ruby, rust
    code: str
    compile_opts: list[str] = field(default_factory=list)
    runtime_opts: list[str] = field(default_factory=list)
    test_cases: list[TestCase] = field(default_factory=list)
    yml_path: Path = field(default_factory=lambda: Path())


# -- Language normalization --

LANG_ALIASES = {
    "c": "c",
    "cpp": "cpp",
    "c++": "cpp",
    "cs": "cs",
    "csharp": "cs",
    "java": "java",
    "openjdk": "java",
    "graalvm": "java",
    "python": "python",
    "ruby": "ruby",
    "rust": "rust",
}

DIR_LANG_PREFIXES = [
    ("java_openjdk", "java"),
    ("java_graalvm", "java"),
    ("python_", "python"),
    ("ruby_", "ruby"),
    ("rust_", "rust"),
    ("cs_", "cs"),
    ("cpp", "cpp"),
    ("java", "java"),
    ("c", "c"),
]


def normalize_lang(raw: str) -> str:
    raw = raw.lower().strip()
    if raw in LANG_ALIASES:
        return LANG_ALIASES[raw]
    raise ValueError(f"Unknown language: {raw!r}")


def lang_from_dir(dirname: str) -> str | None:
    dirname = dirname.lower()
    for prefix, lang in DIR_LANG_PREFIXES:
        if dirname == prefix or dirname.startswith(prefix):
            return lang
    return None


# -- YAML Parsing --


def parse_yml(path: Path, scenario_id: str) -> Scenario:
    """Parse a multi-document YAML scenario file."""
    with open(path) as f:
        docs = list(yaml.safe_load_all(f))

    if not docs or docs[0] is None:
        raise ValueError(f"Empty YAML: {path}")

    main = docs[0]
    name = main.get("name", path.stem)

    raw_lang = main.get("language") or main.get("implementation")
    if raw_lang:
        lang = normalize_lang(raw_lang)
    else:
        inferred = lang_from_dir(path.parent.name)
        if inferred:
            lang = inferred
        else:
            raise ValueError(f"Cannot determine language for: {path}")

    code = main.get("code", "")
    if code and code.startswith("# "):
        # Strip leading comment line (URL reference)
        lines = code.split("\n", 1)
        code = lines[1] if len(lines) > 1 else ""

    compile_opts = main.get("compile_options") or main.get("options") or []
    compile_opts = [str(o) for o in compile_opts]

    runtime_opts = main.get("roptions") or []
    runtime_opts = [str(o) for o in runtime_opts]

    # Build test cases
    test_cases = []

    # CLBG/peter-sestoft style: args in main document
    main_args = main.get("arguments") or main.get("args")
    if main_args is not None:
        test_cases.append(TestCase(
            args=[str(a) for a in main_args],
            expected_stdout=_decode_stdout(main.get("expected_stdout")),
        ))

    # Leetcode style: test cases in subsequent documents
    for doc in docs[1:]:
        if doc is None:
            continue
        doc_args = doc.get("args") or doc.get("arguments")
        if doc_args is not None:
            test_cases.append(TestCase(
                args=[str(a) for a in doc_args],
                expected_stdout=_decode_stdout(doc.get("expected_stdout")),
            ))

    # Fallback: no args anywhere (e.g. sleepers)
    if not test_cases:
        test_cases.append(TestCase(args=[], expected_stdout=None))

    return Scenario(
        id=scenario_id,
        name=name,
        lang=lang,
        code=code,
        compile_opts=compile_opts,
        runtime_opts=runtime_opts,
        test_cases=test_cases,
        yml_path=path,
    )


def _decode_stdout(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


# -- Discovery & Filtering --


def make_scenario_id(yml_path: Path, root: Path) -> str:
    rel = yml_path.relative_to(root)
    parts = [p for p in rel.parts if p != "process"]
    parts[-1] = parts[-1].removesuffix(".yml")
    return "/".join(parts)


def _should_skip(yml_path: Path, root: Path) -> bool:
    rel = yml_path.relative_to(root)
    parts = rel.parts

    # Skip code/ directories
    if any(p in SKIP_DIRS for p in parts):
        return True

    # Skip by category (first dir component)
    if parts[0] in SKIP_CATEGORIES:
        return True

    # Skip huge files
    if yml_path.stat().st_size > MAX_YML_SIZE:
        return True

    # Skip non-English leetcode variants
    stem = yml_path.stem
    if any(stem.endswith(s) for s in SKIP_SUFFIXES):
        return True

    # Skip known-failing scenarios
    scenario_id = make_scenario_id(yml_path, root)
    if scenario_id in SKIP_SCENARIOS:
        return True

    return False


def _should_skip_lang(lang: str) -> bool:
    return lang in SKIP_LANGS


def discover_scenarios_light(root: Path) -> list[tuple[str, str, str, int]]:
    """Lightweight discovery for listing. Returns (id, name, lang, test_count)."""
    results = []
    for yml_path in sorted(root.rglob("*.yml")):
        if _should_skip(yml_path, root):
            continue
        scenario_id = make_scenario_id(yml_path, root)
        try:
            name, lang, test_count = _parse_header(yml_path)
            if _should_skip_lang(lang):
                continue
            results.append((scenario_id, name, lang, test_count))
        except Exception as e:
            print(f"WARNING: {yml_path.name}: {e}", file=sys.stderr)
    return results


def _parse_header(path: Path) -> tuple[str, str, int]:
    """Parse name, language, and test count without loading full file."""
    name = path.stem
    lang = None
    test_count = 0
    in_first_doc = True

    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            stripped = line.strip()
            if stripped == "---":
                in_first_doc = False
                continue
            if in_first_doc:
                m = re.match(r"^name:\s*(.+)", stripped)
                if m:
                    name = m.group(1).strip()
                m = re.match(r"^(?:language|implementation):\s*(.+)", stripped)
                if m:
                    lang = normalize_lang(m.group(1).strip())
            else:
                if re.match(r"^(?:args|arguments):\s", stripped):
                    test_count += 1

    # Check if main doc has args too
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.strip() == "---":
                break
            if re.match(r"^(?:arguments|args):\s", line.strip()):
                test_count += 1
                break

    if lang is None:
        inferred = lang_from_dir(path.parent.name)
        if inferred:
            lang = inferred
        else:
            raise ValueError(f"Cannot determine language")

    if test_count == 0:
        test_count = 1

    return name, lang, test_count


def discover_valid_scenarios(root: Path) -> list[Scenario]:
    """Full parse of all valid scenarios."""
    scenarios = []
    for yml_path in sorted(root.rglob("*.yml")):
        if _should_skip(yml_path, root):
            continue
        scenario_id = make_scenario_id(yml_path, root)
        try:
            scenario = parse_yml(yml_path, scenario_id)
            if _should_skip_lang(scenario.lang):
                continue
            scenarios.append(scenario)
        except Exception as e:
            print(f"WARNING: {yml_path.name}: {e}", file=sys.stderr)
    return scenarios


def find_scenario(root: Path, scenario_id: str) -> Scenario:
    """Find and parse a single scenario by ID."""
    for candidate in _id_to_paths(root, scenario_id):
        if candidate.exists():
            return parse_yml(candidate, scenario_id)

    # Fallback: scan
    for yml_path in root.rglob("*.yml"):
        if _should_skip(yml_path, root):
            continue
        if make_scenario_id(yml_path, root) == scenario_id:
            return parse_yml(yml_path, scenario_id)

    raise FileNotFoundError(f"Scenario not found: {scenario_id}")


def _id_to_paths(root: Path, scenario_id: str) -> list[Path]:
    parts = scenario_id.split("/")
    yml_name = parts[-1] + ".yml"
    prefix = parts[:-1]
    candidates = [root / "/".join(prefix) / yml_name]
    if len(prefix) >= 2:
        candidates.append(
            root / prefix[0] / "process" / "/".join(prefix[1:]) / yml_name
        )
    return candidates


# -- Workspace --

SOURCE_FILES = {
    "c": "program.c",
    "cpp": "program.cpp",
    "java": "Program.java",
    "python": "program.py",
    "ruby": "program.rb",
    "rust": "src/main.rs",
}


def scenario_workdir(workdir: Path, scenario: Scenario) -> Path:
    return workdir / scenario.id


def setup_workspace(scenario: Scenario, sdir: Path, code: str | None = None):
    """Write source code and scaffolding for one scenario."""
    sdir.mkdir(parents=True, exist_ok=True)
    code = code if code is not None else scenario.code
    source_file = SOURCE_FILES[scenario.lang]

    if scenario.lang == "rust":
        (sdir / "src").mkdir(exist_ok=True)
        (sdir / "src" / "main.rs").write_text(code)
        cargo_toml = sdir / "Cargo.toml"
        if not cargo_toml.exists():
            cargo_toml.write_text(textwrap.dedent("""\
                [package]
                name = "scenario"
                version = "0.1.0"
                edition = "2021"
            """))
    else:
        (sdir / source_file).write_text(code)


def get_source_path(scenario: Scenario, sdir: Path) -> Path:
    return sdir / SOURCE_FILES[scenario.lang]


# -- Compilation --


def compile_scenario(scenario: Scenario, sdir: Path) -> subprocess.CompletedProcess:
    lang = scenario.lang
    opts = scenario.compile_opts

    if lang in ("c", "cpp"):
        src_file = "program.c" if lang == "c" else "program.cpp"
        compiler = "gcc" if lang == "c" else "g++"
        code = (sdir / src_file).read_text()

        # Separate compiler flags from linker flags in compile_opts
        compiler_flags = [o for o in opts if not o.startswith("-l")]
        yaml_link_flags = [o for o in opts if o.startswith("-l")]

        link_flags = ["-lm"] + yaml_link_flags
        extra_flags: list[str] = []
        if lang == "cpp":
            link_flags.append("-lpthread")
            if "#include <execution>" in code:
                link_flags.append("-ltbb")
        # Auto-detect APR include path
        if "apr_pools.h" in code:
            extra_flags.extend(["-I/usr/include/apr-1.0"])
        # Auto-detect GMP
        if "gmp.h" in code and "-lgmp" not in link_flags:
            link_flags.append("-lgmp")
        if "gmpxx.h" in code and "-lgmpxx" not in link_flags:
            link_flags.append("-lgmpxx")

        cmd = [compiler] + compiler_flags + extra_flags + ["-o", "program", src_file] + link_flags
    elif lang == "java":
        cmd = ["javac", "Program.java"]
    elif lang == "rust":
        # Split "--config KEY=VALUE" into two args for older cargo versions
        expanded_opts = []
        for o in opts:
            if o.startswith("--config "):
                expanded_opts.extend(["--config", o[len("--config "):]])
            else:
                expanded_opts.append(o)
        cmd = ["cargo", "build"] + expanded_opts
    elif lang in ("python", "ruby"):
        return subprocess.CompletedProcess(args=["true"], returncode=0)
    else:
        raise ValueError(f"Unsupported language: {lang}")

    print(f"  + {shlex.join(cmd)}", file=sys.stderr)
    try:
        return subprocess.run(cmd, cwd=sdir, capture_output=True, text=True)
    except FileNotFoundError:
        print(f"  ERROR: '{cmd[0]}' not found", file=sys.stderr)
        return subprocess.CompletedProcess(args=cmd, returncode=127)


# -- Test Commands --


def get_test_cmd(scenario: Scenario, sdir: Path, test_case: TestCase) -> list[str]:
    lang = scenario.lang
    args = test_case.args

    if lang in ("c", "cpp"):
        return [str(sdir / "program")] + args
    elif lang == "java":
        jvm_opts = scenario.compile_opts
        return ["java"] + jvm_opts + ["-cp", str(sdir), "Program"] + args
    elif lang == "rust":
        binary = sdir / "target" / "release" / "scenario"
        if not binary.exists():
            binary = sdir / "target" / "debug" / "scenario"
        return [str(binary)] + args
    elif lang == "python":
        return ["python3"] + scenario.runtime_opts + [str(sdir / "program.py")] + args
    elif lang == "ruby":
        return ["ruby"] + scenario.runtime_opts + [str(sdir / "program.rb")] + args
    else:
        raise ValueError(f"Unsupported language: {lang}")


def run_test_case(
    scenario: Scenario, sdir: Path, test_case: TestCase, index: int
) -> bool:
    cmd = get_test_cmd(scenario, sdir, test_case)
    args_str = " ".join(test_case.args) if test_case.args else "(no args)"

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        print(f"    FAIL test {index}: command not found: {cmd[0]}")
        return False
    except subprocess.TimeoutExpired:
        print(f"    FAIL test {index}: timeout (args: {args_str})")
        return False

    if result.returncode != 0:
        print(f"    FAIL test {index}: exit code {result.returncode} (args: {args_str})")
        if result.stderr:
            for line in result.stderr.strip().split("\n")[:5]:
                print(f"      {line}")
        return False

    if test_case.expected_stdout is None:
        print(f"    PASS test {index} (args: {args_str})")
        return True

    actual = result.stdout.rstrip("\n")
    expected = test_case.expected_stdout.rstrip("\n")

    if actual == expected:
        print(f"    PASS test {index} (args: {args_str})")
        return True
    else:
        print(f"    FAIL test {index}: output mismatch (args: {args_str})")
        exp_lines = expected.split("\n")
        act_lines = actual.split("\n")
        for i, (e, a) in enumerate(zip(exp_lines, act_lines)):
            if e != a:
                print(f"      expected: {e[:120]}")
                print(f"      actual:   {a[:120]}")
                break
        if len(exp_lines) != len(act_lines):
            print(f"      expected {len(exp_lines)} lines, got {len(act_lines)}")
        return False


def run_tests(scenario: Scenario, sdir: Path) -> bool:
    all_pass = True
    for i, tc in enumerate(scenario.test_cases):
        if not run_test_case(scenario, sdir, tc, i + 1):
            all_pass = False
    return all_pass


# -- CLI Commands --


def cmd_list(args):
    root = Path(args.dir).resolve()
    entries = discover_scenarios_light(root)

    id_w = max((len(e[0]) for e in entries), default=10)
    lang_w = max((len(e[2]) for e in entries), default=4)

    print(f"{'ID':<{id_w}}  {'Lang':<{lang_w}}  Tests")
    print("-" * (id_w + lang_w + 10))
    for sid, name, lang, tc in entries:
        print(f"{sid:<{id_w}}  {lang:<{lang_w}}  {tc}")
    print(f"\n{len(entries)} scenarios")


def cmd_prepare(args):
    root = Path(args.dir).resolve()
    workdir = Path(args.workdir).resolve()
    scenarios = discover_valid_scenarios(root)

    print(f"Extracting {len(scenarios)} scenarios to {workdir}")
    for s in scenarios:
        sdir = scenario_workdir(workdir, s)
        setup_workspace(s, sdir)
        src = get_source_path(s, sdir)
        print(f"  {s.id:<55} -> {src.relative_to(workdir)}")
    print(f"\nDone. Edit source files in {workdir}/, then run build and test.")


def cmd_compile(args):
    root = Path(args.dir).resolve()
    workdir = Path(args.workdir).resolve()

    if args.scenario:
        scenarios = [find_scenario(root, args.scenario)]
    else:
        scenarios = discover_valid_scenarios(root)

    failed = []
    for s in scenarios:
        sdir = scenario_workdir(workdir, s)
        if not sdir.exists():
            print(f"SKIP {s.id} (not prepared)", file=sys.stderr)
            continue
        print(f"Building {s.id}...", file=sys.stderr)
        result = compile_scenario(s, sdir)
        if result.returncode != 0:
            failed.append(s.id)
            print(f"  FAILED (exit {result.returncode})", file=sys.stderr)
            if result.stderr:
                for line in result.stderr.strip().split("\n")[:5]:
                    print(f"    {line}", file=sys.stderr)

    if failed:
        print(f"\n{len(failed)} failed: {', '.join(failed)}", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"\nAll {len(scenarios)} compiled successfully", file=sys.stderr)


def cmd_test(args):
    root = Path(args.dir).resolve()
    workdir = Path(args.workdir).resolve()

    if args.scenario:
        scenarios = [find_scenario(root, args.scenario)]
    else:
        scenarios = discover_valid_scenarios(root)

    passed = 0
    failed = []
    skipped = 0

    for s in scenarios:
        sdir = scenario_workdir(workdir, s)
        if not sdir.exists():
            skipped += 1
            continue
        print(f"  {s.id}")
        if run_tests(s, sdir):
            passed += 1
        else:
            failed.append(s.id)

    print(f"\n{passed} passed, {len(failed)} failed, {skipped} skipped")
    if failed:
        for f in failed:
            print(f"  FAIL: {f}")
        sys.exit(1)


def cmd_test_cmd(args):
    root = Path(args.dir).resolve()
    workdir = Path(args.workdir).resolve()
    scenario = find_scenario(root, args.scenario)
    sdir = scenario_workdir(workdir, scenario)

    for tc in scenario.test_cases:
        print(shlex.join(get_test_cmd(scenario, sdir, tc)))


def cmd_code(args):
    root = Path(args.dir).resolve()
    scenario = find_scenario(root, args.scenario)
    print(scenario.code)


def main():
    parser = argparse.ArgumentParser(
        description="Runner for green-languages-scenarios benchmarks"
    )
    parser.add_argument(
        "--dir",
        required=True,
        help="Path to green-languages-scenarios repository",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List valid scenarios")

    p = sub.add_parser("prepare", help="Extract all code to workspace")
    p.add_argument("--workdir", required=True, help="Workspace directory")

    p = sub.add_parser("compile", help="Compile all or one scenario")
    p.add_argument("scenario", nargs="?", help="Scenario ID (omit for all)")
    p.add_argument("--workdir", required=True, help="Workspace directory")

    p = sub.add_parser("test", help="Test all or one scenario")
    p.add_argument("scenario", nargs="?", help="Scenario ID (omit for all)")
    p.add_argument("--workdir", required=True, help="Workspace directory")

    p = sub.add_parser("test-cmd", help="Print test command for a scenario")
    p.add_argument("scenario", help="Scenario ID")
    p.add_argument("--workdir", required=True, help="Workspace directory")

    p = sub.add_parser("code", help="Print reference source code")
    p.add_argument("scenario", help="Scenario ID")

    args = parser.parse_args()

    {
        "list": cmd_list,
        "prepare": cmd_prepare,
        "compile": cmd_compile,
        "test": cmd_test,
        "test-cmd": cmd_test_cmd,
        "code": cmd_code,
    }[args.command](args)


if __name__ == "__main__":
    main()
