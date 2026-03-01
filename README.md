<p align="center">
  <img src="favicon.png" width="128" height="128" alt="GreenCode Constitution">
</p>

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

### Try it on your own project

Paste the following into your favorite agent extension (e.g., Cursor, Windsurf,
Claude Code, Copilot Chat) to optimize an existing codebase:

> Fetch and read the GreenCode Constitution from
> https://greencode-constitution.org/skill.md (read all of it before analyzing
> the project). Then, audit this project for energy anti-patterns. Try to lower
> energy consumption by at least 5%, doing however many improvements are
> required. Do not stop until you reach that goal. Profile before proposing
> changes and measure the impact of each optimization using the built-in energy
> profiler. In the end, do a final benchmark on baseline. Afterwards, add the
> code per feature, benchmark it, and commit it with information about what
> the commit does plus how much more efficiency it adds. Finally, add an empty
> commit with the end-to-end improvement.

The agent will fetch the constitution, detect project technologies, profile
hotspots, and start proposing principled refactorings, committing each
improvement with measured energy results.

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

## Hacking

To iterate on the constitution and run benchmarks locally, you need an LLM
coding agent that can execute shell commands. Examples below use the
[Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code):

```bash
# macOS, Linux, WSL
curl -fsSL https://claude.ai/install.sh | bash
```

### DGX Spark (GB10) setup

On NVIDIA DGX Spark systems, install the
[SPBM hwmon driver](https://github.com/antheas/spark_hwmon) for hardware
energy accumulators (CPU + GPU). This gives the profiler accurate measurements
without needing `nvidia-smi` or RAPL. Verify with:

```bash
sensors spbm-*
```

### 1. Start the local server

```bash
screen -S const
python3 build.py --test
# Ctrl+A, D to detach
```

This serves `skill.md`, docs, and benchmark scripts at `localhost:3232` with
live regeneration.

### 2. Clone a benchmark repo

```bash
# llama.cpp (LLM inference, CUDA)
git clone https://github.com/antheas/llama.cpp ../llama.cpp

# FFmpeg (video transcoding, CPU + GPU)
git clone https://github.com/FFmpeg/FFmpeg ../FFmpeg

# Pasteur (data synthesis, CPU-bound Python)
git clone https://github.com/pasteur-dev/pasteur ../pasteur

# Scenarios (algorithms, 6 languages)
git clone https://github.com/PLEnergyDev/green-languages-scenarios ../green-languages-scenarios
```

### 3. Run the agent

From inside the benchmark repo, launch your favorite agent with the benchmark
prompt and finalize instructions concatenated.

Examples with the Claude Code CLI:

**llama.cpp:**
```bash
cd ../llama.cpp
claude --dangerously-skip-permissions \
  "$(cat ../greencode-constitution/benches/llamacpp/prompt.md) $(cat ../greencode-constitution/benches/templates/finalize_suffix.md)"
```

**FFmpeg:**
```bash
cd ../FFmpeg
claude --dangerously-skip-permissions \
  "$(cat ../greencode-constitution/benches/ffmpeg/prompt.md) $(cat ../greencode-constitution/benches/templates/finalize_suffix.md)"
```

**Pasteur:**
```bash
cd ../pasteur
claude --dangerously-skip-permissions \
  "$(cat ../greencode-constitution/benches/pasteur/prompt.md) $(cat ../greencode-constitution/benches/templates/finalize_suffix.md)"
```

**Scenarios:**
```bash
cd ../green-languages-scenarios
claude --dangerously-skip-permissions \
  "$(cat ../greencode-constitution/benches/scenarios/prompt.md) $(cat ../greencode-constitution/benches/templates/finalize_suffix.md)"
```

The agent will fetch `localhost:3232/skill.md`, detect the project, run the
benchmark suite, profile hotspots, apply optimizations in a loop, and commit
each improvement with energy measurements. The final empty commit contains the
end-to-end result and the greencode-constitution git hash.

For other agents, pass the contents of `benches/<suite>/prompt.md` and
`benches/templates/finalize_suffix.md` as the initial prompt.

## Acknowledgements

This work was supported by the VILLUM Foundation under project "Teaching AI Green Coding" (VIL70090); by ITEA4 and the Innovation Fund Denmark for projects "GreenCode" (2306) and "MAST" (22035).

## License

See [LICENSE](LICENSE) for details.
