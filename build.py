#!/usr/bin/env python3
"""Build script for GreenCode Constitution.

Scans docs/ to generate skill.md — a single self-contained file
with the constitution and an embedded markdown skill table.
"""

from pathlib import Path

BASE_URL = "https://greencode-constitution.org"
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
    ("*.csproj",           "code/csharp"),
    ("*.sln",              "code/csharp"),
    ("Gemfile",            "code/ruby"),
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


def build_detect_command() -> str:
    """Build the one-liner the agent should run to detect project technologies."""
    filenames = [p for p, _ in DETECT_MAP if "*" not in p]
    name_args = " -o ".join(f'-name "{f}"' for f in filenames)
    return f'find . -maxdepth 3 \\( {name_args} \\) -printf "%f\\n" 2>/dev/null | sort -u'


def build_skill_table() -> str:
    """Build the skill resolution section content."""
    lines = []
    detect_cmd = build_detect_command()

    lines.append("### Detection")
    lines.append("")
    lines.append("Run once to identify project technologies:")
    lines.append("")
    lines.append(f"```sh\n{detect_cmd}\n```")
    lines.append("")
    lines.append("Match output against the table below. Fetch only matching skills from")
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

    return "\n".join(lines)


def build_skill_md(constitution: str, skill_table: str) -> str:
    """Merge constitution with embedded skill table into skill.md."""
    skill_resolution = f"""
## Skill Resolution

The constitution defines *what* to optimize. The *how* lives in skill documents fetched per-technology. Skills win on implementation details; the constitution wins on priority, scope, and conflict resolution. If a skill is unavailable, fall back to constitutional principles and note reduced confidence.

{skill_table}
"""

    parts = constitution.rsplit("## Article VII — Amendments", 1)
    after = parts[1].lstrip("\n")
    return parts[0].rstrip() + "\n" + skill_resolution + "\n---\n\n## Article VII — Amendments\n\n" + after


def main():
    constitution = CONSTITUTION.read_text()
    skill_table = build_skill_table()
    skill_md = build_skill_md(constitution, skill_table)

    SKILL_OUT.write_text(skill_md)
    print(f"wrote {SKILL_OUT} ({len(skill_md.splitlines())} lines)")


if __name__ == "__main__":
    main()
