# Algorithmic Scenarios Benchmark

Energy efficiency benchmark for algorithmic code across multiple languages. Uses problems from LeetCode, the Computer Language Benchmarks Game (CLBG), and Peter Sestoft micro-benchmarks.

## Setup

### 1. Prepare environment

Installs compilers and extracts source code into a workspace:

```bash
bash <(curl -sfL $BASE_URL/benches/scenarios/prepare.sh)
```

Installs: gcc, g++, javac, python3, ruby, cargo/rustc, libboost-dev, libtbb-dev, libgmp-dev, libapr1-dev, uthash-dev

Creates `scenarios-workspace/` with source files organized by scenario ID.

### 2. Build all scenarios

```bash
bash <(curl -sfL $BASE_URL/benches/scenarios/build.sh)
```

Or build a single scenario:

```bash
bash <(curl -sfL $BASE_URL/benches/scenarios/build.sh) SCENARIO_ID
```

### 3. Run tests with profiler

```bash
curl -sfL $BASE_URL/benches/scenarios/test.sh > /tmp/scenarios-test.sh && chmod +x /tmp/scenarios-test.sh && bash <(curl -sfL $BASE_URL/profile.sh || echo exit 1) -- /tmp/scenarios-test.sh
```

Or test a single scenario:

```bash
curl -sfL $BASE_URL/benches/scenarios/test.sh > /tmp/scenarios-test.sh && chmod +x /tmp/scenarios-test.sh && bash <(curl -sfL $BASE_URL/profile.sh || echo exit 1) -- /tmp/scenarios-test.sh SCENARIO_ID
```

## Workflow

After prepare, `run.py` is cached at `/tmp/scenarios-run.py`. Use these wrappers:

1. List scenarios: `bash <(curl -sfL $BASE_URL/benches/scenarios/list.sh)`
2. View reference code: `bash <(curl -sfL $BASE_URL/benches/scenarios/code.sh) SCENARIO_ID`
3. Edit source file in `scenarios-workspace/SCENARIO_ID/`
4. Rebuild: `bash <(curl -sfL $BASE_URL/benches/scenarios/build.sh) SCENARIO_ID`
5. Verify: `bash <(curl -sfL $BASE_URL/benches/scenarios/test.sh) SCENARIO_ID`
6. Repeat for other scenarios
7. Final energy measurement: wrap test.sh with the profiler (see step 3 above)

## Source file locations

Each scenario at `scenarios-workspace/SCENARIO_ID/`:

| Language | File |
|----------|------|
| C | `program.c` |
| C++ | `program.cpp` |
| Java | `Program.java` |
| Python | `program.py` |
| Ruby | `program.rb` |
| Rust | `src/main.rs` |

## Language Skills

Fetch the relevant optimization guides before working on each language:

| Language | Skill URL |
|----------|-----------|
| C, C++ | `$BASE_URL/docs/code/c-cpp.md` |
| Java | `$BASE_URL/docs/code/java.md` |
| Python | `$BASE_URL/docs/code/python.md` |
| Ruby | `$BASE_URL/docs/code/ruby.md` |

Rust has no dedicated skill — apply constitutional principles directly.

## Benchmark Details

- **LeetCode:** n-queens, group-anagrams, word-ladder-2 (C, C++, Java, Python, Ruby, Rust)
- **CLBG:** binary-trees, fannkuch-redux, n-body, spectral-norm, pidigits (C, C++, Java)
- **Peter Sestoft:** division-loop, matrix-multiplication, polynomial-evaluation (C, C++, Java, Rust)
- **Total:** ~45 scenarios across 6 languages
- **Verification:** Output compared against known-good expected values
