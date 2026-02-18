#!/usr/bin/env python3
"""Build script for GreenCode Constitution.

Scans docs/ to generate skill.md — a single self-contained file
with the constitution and an embedded markdown skill table.

With --test, serves a local web server that dynamically generates skill.md.
"""

import argparse
import http.server
import socketserver
from functools import partial
from pathlib import Path

DEFAULT_BASE_URL = "https://greencode-constitution.org"
BASE_URL = DEFAULT_BASE_URL
ROOT = Path(__file__).parent
DOCS = ROOT / "docs"
CONSTITUTION = ROOT / "constitution.md"
SKILL_OUT = ROOT / "skill.md"

# Map from file/pattern found in a project -> which skill doc to fetch.
DETECT_MAP = [
    # Code skills
    ("requirements.txt",   "code/python"),
    ("pyproject.toml",     "code/python"),
    ("Pipfile",            "code/python"),
    ("pom.xml",            "code/java"),
    ("build.gradle",       "code/java"),
    ("package.json",       "code/javascript"),
    ("tsconfig.json",      "code/javascript"),
    ("CMakeLists.txt",     "code/c-cpp"),
    ("Makefile",           "code/c-cpp"),
    ("*.cu",               "code/cuda"),
    ("*.cuh",              "code/cuda"),
    ("*.csproj",           "code/csharp"),
    ("*.sln",              "code/csharp"),
    ("Gemfile",            "code/ruby"),
    ("go.mod",             "code/go"),
    ("go.sum",             "code/go"),
    # Architecture skills
    ("Dockerfile",         "architecture/docker"),
    ("docker-compose.yml", "architecture/docker"),
    ("*.tf",               "architecture/terraform"),
    ("serverless.yml",     "architecture/aws"),
    ("template.yaml",      "architecture/aws"),
    ("app.yaml",           "architecture/gcp"),
    ("cloudbuild.yaml",    "architecture/gcp"),
    ("kustomization.yaml", "architecture/kubernetes"),
    ("helmfile.yaml",      "architecture/kubernetes"),
    ("Chart.yaml",         "architecture/kubernetes"),
    ("postgresql.conf",    "architecture/postgresql"),
    ("my.cnf",             "architecture/mysql"),
    ("redis.conf",         "architecture/redis"),
]

GUIDE_DEFS = [
    ("cloud",          "Cloud energy patterns (Green Software Foundation)"),
    ("detection",      "Cross-language grep/regex detection patterns"),
    ("arch-detection", "CLI commands and PromQL for infrastructure audits"),
    ("overview",       "Anti-pattern overview with rationale and references"),
]

# Benchmark detection: check for specific project indicators
BENCH_DETECT_MAP = [
    ("llama.cpp", ["ggml/", "CMakeLists.txt"]),  # llama.cpp has ggml/ directory
    ("pasteur", ["src/pasteur/", "conf/"]),  # pasteur has src/pasteur/ and conf/ directories
]

BENCH_DEFS = [
    ("llamacpp", "llama.cpp inference with Qwen3-8B (488 input / 512 output tokens)"),
    ("pasteur", "Pasteur data synthesis pipeline (mimic_core.mare)"),
]

BENCHES_TEMPLATES = ROOT / "benches" / "templates"


def build_detect_command() -> str:
    """Build the one-liner the agent should run to detect project technologies and benchmarks."""
    return f'bash <(curl -sfL {BASE_URL}/detect.sh)'


def generate_detect_script() -> str:
    """Generate detect.sh script content from DETECT_MAP and BENCH_DETECT_MAP."""
    lines = ["#!/bin/bash"]
    lines.append("# Auto-generated detection script for GreenCode Constitution")
    lines.append("# Detects project technologies and available benchmarks")
    lines.append("")
    lines.append("set -euo pipefail")
    lines.append("")
    lines.append("# Detect technologies by finding marker files")

    # Build find command from DETECT_MAP
    filenames = [p for p, _ in DETECT_MAP if "*" not in p]
    name_args = " -o ".join(f'-name "{f}"' for f in filenames)
    lines.append(f'find . -maxdepth 3 \\( {name_args} \\) -printf "%f\\n" 2>/dev/null | sort -u')
    lines.append("")

    # Add benchmark detection
    lines.append("# Detect available benchmarks")
    for bench_name, indicators in BENCH_DETECT_MAP:
        conditions = []
        for indicator in indicators:
            if indicator.endswith("/"):
                conditions.append(f'[ -d "{indicator.rstrip("/")}" ]')
            else:
                conditions.append(f'[ -f "{indicator}" ]')

        # Special case for llama.cpp - also check CMakeLists.txt content
        if bench_name == "llama.cpp":
            conditions.append('grep -q "llama" CMakeLists.txt 2>/dev/null')

        condition_str = " && ".join(conditions)
        lines.append(f'{condition_str} && echo "{bench_name} [bench]"')

    return "\n".join(lines) + "\n"


def build_skill_table() -> str:
    """Build the skill resolution section content."""
    lines = []
    detect_cmd = build_detect_command()

    lines.append("### Detection")
    lines.append("")
    lines.append("Run once to identify project technologies and benchmarks:")
    lines.append("")
    lines.append(f"```sh\n{detect_cmd}\n```")
    lines.append("")
    lines.append("Match output against the tables below. Fetch only matching skills from")
    lines.append(f"`{BASE_URL}/docs/{{path}}.md`.")
    lines.append("")

    lines.append("### Pattern to Skill")
    lines.append("")
    lines.append("| Pattern | Skill |")
    lines.append("|---------|-------|")
    for pattern, skill in DETECT_MAP:
        if (DOCS / f"{skill}.md").exists():
            lines.append(f"| {pattern} | {skill} |")

    lines.append("")

    lines.append("### Guides")
    lines.append("")
    lines.append(f"Fetch from `{BASE_URL}/docs/{{guide}}.md` when needed.")
    lines.append("")
    lines.append("| ID | Description |")
    lines.append("|----|-------------|")
    for guide_id, description in GUIDE_DEFS:
        if (DOCS / f"{guide_id}.md").exists():
            lines.append(f"| {guide_id} | {description} |")

    lines.append("")

    lines.append("### Benchmarks")
    lines.append("")
    lines.append(f"Fetch from `{BASE_URL}/benches/{{bench}}.md` when detected.")
    lines.append("")
    lines.append("| Detection Output | Benchmark | Description |")
    lines.append("|------------------|-----------|-------------|")
    for bench_id, description in BENCH_DEFS:
        bench_template = BENCHES_TEMPLATES / f"{bench_id}.md"
        if bench_template.exists():
            # Map bench_id to detection output name
            detect_names = {"llamacpp": "llama.cpp"}
            detect_name = detect_names.get(bench_id, bench_id)
            lines.append(f"| {detect_name} [bench] | {bench_id} | {description} |")

    return "\n".join(lines)


def build_profiling_section() -> str:
    """Build the energy profiling section by embedding docs/profiling.md content."""
    profiling_doc = (DOCS / "profiling.md").read_text()
    # Replace $BASE_URL placeholder in the profiling doc
    profiling_doc = profiling_doc.replace("$BASE_URL", BASE_URL)

    return f"""## Energy Profiling

Measure actual energy before/after optimization:

```bash
bash <(curl -sfL {BASE_URL}/profile.sh || echo exit 1) -- <command>
```

Outputs CPU joules (RAPL/perf), GPU joules (nvidia-smi/rocm-smi/sysfs), wall/CPU time.

{profiling_doc}"""




def build_skill_md(constitution: str, skill_table: str) -> str:
    """Merge constitution with embedded skill table into skill.md."""
    profiling = build_profiling_section()
    skill_resolution = f"""
## Skill Resolution

The constitution defines *what* to optimize. The *how* lives in skill documents fetched per-technology. Skills win on implementation details; the constitution wins on priority, scope, and conflict resolution. If a skill is unavailable, fall back to constitutional principles and note reduced confidence.

{skill_table}

---

{profiling}
"""

    parts = constitution.rsplit("## Article VII — Amendments", 1)
    after = parts[1].lstrip("\n")
    return parts[0].rstrip() + "\n" + skill_resolution + "\n---\n\n## Article VII — Amendments\n\n" + after


def generate_skill_md() -> str:
    """Generate skill.md content on the fly."""
    constitution = CONSTITUTION.read_text()
    skill_table = build_skill_table()
    return build_skill_md(constitution, skill_table)


class DynamicHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler that dynamically generates skill.md and replaces $BASE_URL in docs."""

    def __init__(self, *args, directory=None, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self):
        if self.path == "/skill.md" or self.path == "/skill.md?":
            content = generate_skill_md().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/markdown; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == "/detect.sh":
            # Generate detect.sh dynamically from DETECT_MAP
            content = generate_detect_script().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/x-shellscript")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        elif self.path in ("/profile.sh", "/energy-profile.py"):
            # Serve tools/* at top level, replacing BASE_URL in profile.sh
            file_path = ROOT / "tools" / self.path.lstrip("/")
            if file_path.exists():
                content = file_path.read_text()
                if self.path == "/profile.sh":
                    content = content.replace(
                        'BASE_URL="${GREENCODE_BASE_URL:-https://greencode-constitution.org}"',
                        f'BASE_URL="${{GREENCODE_BASE_URL:-{BASE_URL}}}"'
                    )
                content = content.encode("utf-8")
                self.send_response(200)
                ctype = "text/x-shellscript" if self.path.endswith(".sh") else "text/x-python"
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404)
        elif self.path.startswith("/benches/"):
            # Serve benchmark files - .md from templates/, scripts from benches/
            if self.path.endswith(".md"):
                # Serve from templates directory
                filename = Path(self.path).name
                file_path = ROOT / "benches" / "templates" / filename
            else:
                # Serve scripts directly from benches/
                file_path = ROOT / self.path.lstrip("/")

            if file_path.exists():
                content = file_path.read_text()
                # Replace $BASE_URL in bench docs
                if self.path.endswith(".md"):
                    content = content.replace("$BASE_URL", BASE_URL)
                content = content.encode("utf-8")
                self.send_response(200)
                if self.path.endswith(".sh"):
                    ctype = "text/x-shellscript"
                elif self.path.endswith(".md"):
                    ctype = "text/markdown; charset=utf-8"
                else:
                    ctype = "text/plain"
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404)
        elif self.path.startswith("/docs/") and self.path.endswith(".md"):
            # Replace $BASE_URL in doc files
            file_path = ROOT / self.path.lstrip("/")
            if file_path.exists():
                content = file_path.read_text().replace("$BASE_URL", BASE_URL)
                content = content.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/markdown; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404)
        else:
            super().do_GET()


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


def run_server(port: int):
    """Run the test server with dynamic skill.md generation."""
    global BASE_URL
    BASE_URL = f"http://localhost:{port}"

    handler = partial(DynamicHandler, directory=str(ROOT))
    with ReusableTCPServer(("", port), handler) as httpd:
        print(f"Serving at http://localhost:{port}")
        print(f"skill.md available at http://localhost:{port}/skill.md (dynamically generated)")
        print("Press Ctrl+C to stop")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down...")
            httpd.shutdown()


def main():
    parser = argparse.ArgumentParser(description="Build or serve GreenCode Constitution skill.md")
    parser.add_argument("--test", action="store_true", help="Run local test server")
    parser.add_argument("-p", "--port", type=int, default=3232, help="Port for test server (default: 3232)")
    args = parser.parse_args()

    if args.test:
        run_server(args.port)
    else:
        skill_md = generate_skill_md()
        SKILL_OUT.write_text(skill_md)
        print(f"wrote {SKILL_OUT} ({len(skill_md.splitlines())} lines)")

        # Copy tools to top level for simpler URLs
        import shutil
        for name in ("profile.sh", "energy-profile.py"):
            src = ROOT / "tools" / name
            dst = ROOT / name
            if src.exists():
                shutil.copy2(src, dst)
        print("copied tools/{profile.sh,energy-profile.py} to top level")

        # Generate detect.sh from DETECT_MAP
        detect_script = generate_detect_script()
        (ROOT / "detect.sh").write_text(detect_script)
        print("generated detect.sh from DETECT_MAP")

        # Process benchmark docs from templates/ - replace $BASE_URL for static hosting
        templates_dir = ROOT / "benches" / "templates"
        benches_dir = ROOT / "benches"
        if templates_dir.exists():
            for template_file in templates_dir.glob("*.md"):
                content = template_file.read_text()
                processed = content.replace("$BASE_URL", DEFAULT_BASE_URL)
                output_file = benches_dir / template_file.name
                output_file.write_text(processed)
                print(f"processed {template_file.name} -> benches/{template_file.name}")


if __name__ == "__main__":
    main()
