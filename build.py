#!/usr/bin/env python3
"""Build script for GreenCode Constitution.

Scans docs/ to generate manifest.json, then merges it with constitution.md
to produce skill.md — a single self-contained file an agent can fetch once.
"""

import json
import re
from pathlib import Path

BASE_URL = "https://greencode-constitution.org"
ROOT = Path(__file__).parent
DOCS = ROOT / "docs"
CONSTITUTION = ROOT / "constitution.md"
MANIFEST_OUT = ROOT / "manifest.json"
SKILL_OUT = ROOT / "skill.md"

# File patterns that indicate a language or technology is present in a codebase.
SKILL_DEFS = {
    "code": {
        "python":     {"detect": ["*.py", "requirements.txt", "pyproject.toml", "Pipfile", "setup.py", "setup.cfg"]},
        "java":       {"detect": ["*.java", "pom.xml", "build.gradle", "build.gradle.kts"]},
        "javascript": {"detect": ["*.js", "*.ts", "*.tsx", "*.jsx", "package.json", "tsconfig.json"]},
        "c-cpp":      {"detect": ["*.c", "*.cpp", "*.cc", "*.cxx", "*.h", "*.hpp", "CMakeLists.txt", "Makefile"]},
        "csharp":     {"detect": ["*.cs", "*.csproj", "*.sln"]},
        "ruby":       {"detect": ["*.rb", "Gemfile", "Rakefile", "*.gemspec"]},
        "sql":        {"detect": ["*.sql", "migrations/", "db/"]},
    },
    "architecture": {
        "aws":        {"detect": ["aws-cdk", "serverless.yml", "template.yaml", "cloudformation", ".aws/"]},
        "gcp":        {"detect": ["app.yaml", "cloudbuild.yaml", ".gcloudignore"]},
        "kubernetes": {"detect": ["kustomization.yaml", "helmfile.yaml", "Chart.yaml"]},
        "docker":     {"detect": ["Dockerfile", "docker-compose.yml", "docker-compose.yaml", ".dockerignore"]},
        "postgresql": {"detect": ["postgresql.conf", "pg_hba.conf"]},
        "mysql":      {"detect": ["my.cnf", "my.ini"]},
        "redis":      {"detect": ["redis.conf"]},
        "terraform":  {"detect": ["*.tf", "*.tfvars", ".terraform/", "terraform.tfstate"]},
    },
}

# Principle IDs are extracted from skill docs by scanning for headings/content
# that map to known constitutional principle keywords.
PRINCIPLE_KEYWORDS = {
    "C1": ["n\\+1", "select_related", "prefetch_related", "includes\\(", "joinedload", "eager"],
    "C2": ["unbuffered", "buffered", "fgetc", "fputc", "BufferedReader", "BufferedWriter"],
    "C3": ["string concatenat", "StringBuilder", "StringBuffer", "\\.join\\(", "strcat"],
    "C4": ["missing index", "CREATE INDEX", "add_index", "full table scan"],
    "C5": ["recursive event", "infinite loop", "recursive lambda"],
    "C6": ["memoiz", "lru_cache", "@cache", "fibonacci"],
    "C7": ["idle", "unused", "underutilized"],
    "C8": ["batch", "bulk", "executemany", "bulk_create", "insert_all", "saveAll"],
    "H1": ["async", "non-blocking", "readFileSync", "writeFileSync", "synchronous"],
    "H2": ["object.*loop", "new.*inside.*loop", "instantiat.*loop", "allocation.*loop"],
    "H3": ["try-with-resource", "context manager", "with open", "close\\(\\)", "IDisposable", "using \\("],
    "H4": ["SELECT \\*", "select\\(\\*\\)"],
    "H5": ["compress", "gzip", "brotli", "GZipMiddleware", "compression\\(\\)"],
    "H6": ["HashSet", "HashMap", "Set\\(\\)", "includes.*loop", "contains.*loop", "include\\?.*loop"],
    "H7": ["auto-scal", "autoscal", "HPA"],
    "H8": ["cache", "CDN", "CloudFront", "Redis"],
    "H9": ["LIMIT", "pagination", "unbounded"],
    "H10": ["inter-service", "chatty", "microservice"],
    "H11": ["queue", "background", "defer"],
    "H12": ["stateless"],
    "R1": ["pre-siz", "initial capacity", "reserve\\("],
    "R2": ["invariant", "loop-invariant", "hoist"],
    "R3": ["protobuf", "MessagePack", "serializ"],
    "R11": ["autobox", "boxing"],
    "R12": ["collection type", "ArrayList.*LinkedList", "wrong.*collection"],
    "N5": ["bundle", "tree-shak", "code-split", "lazy-load"],
}


def count_antipatterns(text: str) -> int:
    """Count anti-pattern entries by looking for '## ' or '### ' section headings
    that contain keywords like 'anti-pattern', 'detect', or numbered patterns."""
    headings = re.findall(r"^##+ \d+\.", text, re.MULTILINE)
    if headings:
        return len(headings)
    # Fallback: count h2/h3 that look like pattern entries (skip the title)
    headings = re.findall(r"^## .+", text, re.MULTILINE)
    return max(len(headings) - 1, 0)


def detect_principles(text: str) -> list[str]:
    """Scan skill doc text for principle keyword matches."""
    found = []
    text_lower = text.lower()
    for pid, keywords in PRINCIPLE_KEYWORDS.items():
        for kw in keywords:
            if re.search(kw, text_lower):
                found.append(pid)
                break
    # Sort by tier order
    tier_order = {"C": 0, "H": 1, "R": 2, "N": 3}
    found.sort(key=lambda p: (tier_order.get(p[0], 9), int(re.search(r"\d+", p).group())))
    return found


def build_manifest() -> dict:
    """Scan docs/ and build the manifest."""
    manifest = {"version": "1.0", "base_url": BASE_URL, "skills": {"code": [], "architecture": []}, "guides": []}

    for category, skills in SKILL_DEFS.items():
        doc_dir = DOCS / category
        for skill_id, meta in skills.items():
            doc_path = doc_dir / f"{skill_id}.md"
            if not doc_path.exists():
                continue
            text = doc_path.read_text()
            entry = {
                "id": skill_id,
                "path": f"/docs/{category}/{skill_id}.md",
                "detect": meta["detect"],
                "principles": detect_principles(text),
                "antipatterns": count_antipatterns(text),
            }
            manifest["skills"][category].append(entry)

    # Guides: top-level docs that aren't the constitution
    guide_meta = {
        "cloud.md": {"id": "cloud-patterns", "description": "Cloud energy patterns from the Green Software Foundation catalog."},
        "code-level-energy-antipatterns-detection.md": {"id": "code-detection", "description": "Cross-language grep/regex detection patterns."},
        "architecture-energy-antipatterns-cli-detection.md": {"id": "architecture-detection", "description": "CLI commands and PromQL queries for infrastructure audits."},
        "energy-efficient-coding-antipatterns.md": {"id": "overview", "description": "Comprehensive anti-pattern overview with rationale and references."},
    }
    for filename, meta in guide_meta.items():
        path = DOCS / filename
        if path.exists():
            manifest["guides"].append({"id": meta["id"], "path": f"/docs/{filename}", "description": meta["description"]})

    return manifest


def compact_constitution(text: str) -> str:
    """Remove the old Article VII GET-request protocol since manifest is now embedded."""
    # Remove Article VII (Skill Resolution Protocol) entirely — it will be replaced
    # by a short note that the manifest is embedded below.
    text = re.sub(
        r"---\s*\n## Article VII — Skill Resolution Protocol.*?(?=---\s*\n## Article VIII)",
        "",
        text,
        flags=re.DOTALL,
    )
    # Renumber Article VIII -> Article VII
    text = text.replace("## Article VIII — Amendments", "## Article VII — Amendments")
    # Remove excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def build_skill_md(constitution: str, manifest: dict) -> str:
    """Merge compacted constitution with embedded manifest into skill.md."""
    manifest_json = json.dumps(manifest, indent=2)

    skill_resolution = """
## Skill Resolution

The constitution defines *what* to optimize. The *how* lives in language- and technology-specific skill documents listed below. The agent scans the target codebase for file patterns and fetches only matching skills from `{base_url}{{skill.path}}`.

When a skill provides a more specific instruction than the constitution, the skill wins on implementation details. The constitution wins on priority, scope, and conflict resolution.

If a skill is unavailable, fall back to the constitutional principle text and note reduced confidence.

### Manifest

```json
{manifest_json}
```
""".format(base_url=manifest["base_url"], manifest_json=manifest_json)

    # Insert skill resolution before the Amendments article
    parts = constitution.rsplit("## Article VII — Amendments", 1)
    return parts[0].rstrip() + "\n" + skill_resolution + "\n---\n\n## Article VII — Amendments\n" + parts[1]


def main():
    constitution_text = CONSTITUTION.read_text()
    manifest = build_manifest()

    # Write standalone manifest.json
    MANIFEST_OUT.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {MANIFEST_OUT}")

    # Compact constitution and merge with manifest into skill.md
    compacted = compact_constitution(constitution_text)
    skill_md = build_skill_md(compacted, manifest)
    SKILL_OUT.write_text(skill_md)
    print(f"wrote {SKILL_OUT}")

    # Stats
    orig_lines = len(constitution_text.splitlines())
    skill_lines = len(skill_md.splitlines())
    n_skills = len(manifest["skills"]["code"]) + len(manifest["skills"]["architecture"])
    n_guides = len(manifest["guides"])
    print(f"constitution: {orig_lines} lines -> skill.md: {skill_lines} lines")
    print(f"manifest: {n_skills} skills, {n_guides} guides")


if __name__ == "__main__":
    main()
