# GreenCode Constitution

A structured hierarchy of energy-efficiency principles for guiding LLM agents in automated code optimization.

**Website:** [greencode-constitution.org](https://greencode-constitution.org)

## What is it?

GreenCode Constitution is an agentic framework that equips LLMs with a hierarchy of energy-efficiency principles for automatically detecting and refactoring energy anti-patterns in existing codebases. Rather than relying on ad hoc prompting, the agent evaluates candidate refactorings against a rubric spanning algorithmic complexity, memory behavior, and infrastructure utilization.

## Quick start

```bash
# 1. Fetch the skill document
curl -sfL https://greencode-constitution.org/skill.md -o skill.md

# 2. Add to your agent (e.g., Claude Code)
cp skill.md .claude/skill-greencode.md

# 3. Measure energy
bash <(curl -sfL https://greencode-constitution.org/profile.sh) -- python my_app.py
```

## Structure

| Path | Description |
|------|-------------|
| `constitution.md` | Core document: 5 meta-principles, 37 anti-patterns across 4 tiers, conflict resolution, scope guards, self-critique protocol |
| `skill.md` | Generated: constitution + skill resolution table + profiling docs |
| `docs/code/` | Language skills: Python, Java, JavaScript, C/C++, CUDA, C#, Go, Ruby, SQL |
| `docs/architecture/` | Infrastructure skills: Docker, Kubernetes, Terraform, AWS, GCP, PostgreSQL, MySQL, Redis |
| `docs/` | Guides: detection patterns, cloud energy, architecture audits, anti-pattern overview |
| `benches/` | Benchmark suites: llama.cpp, FFmpeg, Pasteur, Scenarios |
| `tools/` | Energy profiler (RAPL, perf, SPBM hwmon, nvidia-smi, smart plug) |
| `build.py` | Generates `skill.md`, `detect.sh`, and processes benchmark templates |

## Results

| Benchmark | Reduction | Method |
|-----------|-----------|--------|
| llama.cpp | 5% GPU | CUDA kernel fusions (nvidia-smi) |
| FFmpeg | 13.5% total | 4K GPU transcoding (SPBM) |
| Pasteur | 32.5% total | Data synthesis pipeline (SPBM) |
| Scenarios | 21% total | 45 problems, 6 languages (SPBM) |

## Building

```bash
# Generate static files (skill.md, detect.sh, profile.sh, bench docs)
python3 build.py

# Run local dev server with dynamic generation
python3 build.py --test
```

## License

See [LICENSE](LICENSE) for details.
