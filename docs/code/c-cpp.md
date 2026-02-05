# C / C++ Energy Anti-Patterns: Detection & Fix Guide

> Agent skill: scan a C/C++ codebase for energy-wasting patterns and apply fixes.

---

## How to Use This Skill

1. Run the **Detect** command for each anti-pattern against the project source tree.
2. Review each match — not every hit is a true positive; use context.
3. Apply the **Fix** pattern, adapting to the surrounding code.

---

## Profiling Tools

Before pattern-matching, identify actual hotspots with profiling. Optimize what's measured, not what's guessed.

### CPU Profiling

**perf** (Linux, kernel-level, low overhead):
```bash
perf record -g ./your_program
perf report
# Flamegraph:
perf script | stackcollapse-perf.pl | flamegraph.pl > flame.svg
```

**gprof** (compile-time instrumentation):
```bash
gcc -pg -o your_program your_program.c
./your_program
gprof your_program gmon.out > analysis.txt
```

**Valgrind Callgrind** (detailed but slow):
```bash
valgrind --tool=callgrind ./your_program
kcachegrind callgrind.out.*
```

### Memory Profiling

**Valgrind Massif** (heap profiler):
```bash
valgrind --tool=massif ./your_program
ms_print massif.out.*
```

**AddressSanitizer** (leak detection, compile-time):
```bash
gcc -fsanitize=address -g -o your_program your_program.c
./your_program
```

---

## 1. `strlen()` in Loop Condition

**Why it wastes energy**: `strlen()` is O(n) — it scans until the null terminator every time. In a loop condition, this turns an O(n) loop into O(n²).

### Detect

```bash
grep -rEn 'for *\(.*;.*strlen\(' --include="*.c" --include="*.cpp" --include="*.h" --include="*.hpp" ./src
grep -rEn 'while *\(.*strlen\(' --include="*.c" --include="*.cpp" ./src
```

### Bad

```c
for (int i = 0; i < strlen(str); i++) {  // O(n) call on every iteration
    process(str[i]);
}
```

### Fix

```c
size_t len = strlen(str);
for (size_t i = 0; i < len; i++) {
    process(str[i]);
}
```

---

## 2. Unbuffered I/O — Character-at-a-Time Read/Write

**Why it wastes energy**: Each `fgetc()` / `fputc()` or `read(fd, &ch, 1)` may trigger a system call. Reading in blocks reduces syscall overhead by orders of magnitude.

### Detect

```bash
# Single-byte read/write calls
grep -rEn 'fgetc\(|fputc\(|getc\(|putc\(' --include="*.c" --include="*.cpp" ./src
grep -rEn 'read\(.*,.*1\)' --include="*.c" --include="*.cpp" ./src
grep -rEn 'write\(.*,.*1\)' --include="*.c" --include="*.cpp" ./src
```

### Bad

```c
FILE *f = fopen("data.bin", "rb");
int ch;
while ((ch = fgetc(f)) != EOF) {
    process(ch);
}
```

### Fix

```c
FILE *f = fopen("data.bin", "rb");
char buf[4096];
size_t n;
while ((n = fread(buf, 1, sizeof(buf), f)) > 0) {
    for (size_t i = 0; i < n; i++) {
        process(buf[i]);
    }
}
```

---

## 3. Allocating Memory Inside Loops (`malloc` / `new`)

**Why it wastes energy**: Heap allocation is expensive. Allocating inside a loop and freeing each iteration creates heavy allocator pressure.

### Detect

```bash
# malloc/calloc/realloc inside loops
grep -rEn '(for|while)' -A15 --include="*.c" ./src | grep -E '(malloc|calloc|realloc)\('

# C++ new inside loops
grep -rEn '(for|while)' -A15 --include="*.cpp" ./src | grep -E '\bnew [A-Z]'
```

### Bad

```c
for (int i = 0; i < n; i++) {
    char *buf = malloc(256);
    snprintf(buf, 256, "item %d", i);
    process(buf);
    free(buf);
}
```

### Fix

```c
char buf[256];  // stack allocation, reused each iteration
for (int i = 0; i < n; i++) {
    snprintf(buf, 256, "item %d", i);
    process(buf);
}
```

---

## 4. String Concatenation with `strcat()` in Loops

**Why it wastes energy**: `strcat()` scans to the end of the destination string each call — O(n) per call, O(n²) total in a loop.

### Detect

```bash
grep -rEn '(for|while)' -A15 --include="*.c" --include="*.cpp" ./src | grep -E 'strcat\('
```

### Bad

```c
char result[10000] = "";
for (int i = 0; i < 1000; i++) {
    char temp[16];
    snprintf(temp, sizeof(temp), "%d,", i);
    strcat(result, temp);  // re-scans result each time
}
```

### Fix

```c
char result[10000];
int offset = 0;
for (int i = 0; i < 1000; i++) {
    offset += snprintf(result + offset, sizeof(result) - offset, "%d,", i);
}
```

---

## 5. Missing Resource Cleanup (File Handles, Memory)

**Why it wastes energy**: Leaked file descriptors and memory exhaust OS resources and increase swap pressure.

### Detect

```bash
# fopen without corresponding fclose
grep -rEn 'fopen\(' --include="*.c" --include="*.cpp" ./src

# malloc without free (requires manual review)
grep -rEn 'malloc\(' --include="*.c" --include="*.cpp" ./src

# C++ new without corresponding delete
grep -rEn '\bnew [A-Z]' --include="*.cpp" ./src
```

### Fix

For C, ensure every `fopen` has a matching `fclose` and every `malloc` a matching `free`, including on error paths. For C++, prefer RAII:

```cpp
// Bad
FILE *f = fopen("data.txt", "r");
// ... might return early without fclose

// Good (C++)
std::ifstream f("data.txt");
// automatically closed when f goes out of scope

// Good (C++ for heap memory)
auto ptr = std::make_unique<MyType>();
// automatically freed when ptr goes out of scope
```

---

## 6. Invariant Computation Inside Loops

**Why it wastes energy**: Expressions whose result doesn't change are re-evaluated every iteration.

### Detect

```bash
grep -rEn '(for|while)' -A15 --include="*.c" --include="*.cpp" ./src | grep -E '(sqrt|pow|sin|cos|log|exp|strlen)\('
```

### Bad

```c
for (int i = 0; i < n; i++) {
    double factor = sqrt(base) * M_PI;
    result[i] = data[i] * factor;
}
```

### Fix

```c
double factor = sqrt(base) * M_PI;
for (int i = 0; i < n; i++) {
    result[i] = data[i] * factor;
}
```

---

## 7. C++ `std::string` Concatenation in Loops

**Why it wastes energy**: Same immutable-copy problem as other languages, though `std::string` in C++ does have a small buffer optimization. Still, `+=` in a loop can trigger multiple reallocations.

### Detect

```bash
grep -rEn '(for|while)' -A15 --include="*.cpp" ./src | grep -E 'std::string.*\+='
grep -rEn '(for|while)' -A15 --include="*.cpp" ./src | grep -E '\+= *"'
```

### Bad

```cpp
std::string result;
for (int i = 0; i < 10000; i++) {
    result += std::to_string(i) + ",";
}
```

### Fix

```cpp
std::ostringstream oss;
for (int i = 0; i < 10000; i++) {
    oss << i << ",";
}
std::string result = oss.str();

// Or pre-reserve:
std::string result;
result.reserve(estimated_size);
for (int i = 0; i < 10000; i++) {
    result += std::to_string(i);
    result += ',';
}
```

---

## 8. Copying Instead of Moving (C++11+)

**Why it wastes energy**: Returning or passing large objects by value without move semantics triggers deep copies.

### Detect

```bash
# push_back without std::move on temporary or local variable
grep -rEn 'push_back\(' --include="*.cpp" ./src | grep -v 'std::move\|emplace'

# Returning local vectors/strings (usually RVO handles this, but check)
grep -rEn 'return \w+;' --include="*.cpp" ./src
```

### Fix

```cpp
// Use emplace_back instead of push_back where possible
vec.emplace_back(arg1, arg2);  // constructs in-place

// Use std::move when transferring ownership
vec.push_back(std::move(local_string));
```

---

## 9. Not Pre-sizing `std::vector`

**Why it wastes energy**: `std::vector` doubles its capacity on resize, causing reallocation and element copies.

### Detect

```bash
grep -rEn 'std::vector<' --include="*.cpp" --include="*.hpp" ./src | grep -v 'reserve\|\.capacity'
```

### Bad

```cpp
std::vector<int> v;
for (int i = 0; i < 100000; i++) {
    v.push_back(i);  // ~17 reallocations
}
```

### Fix

```cpp
std::vector<int> v;
v.reserve(100000);
for (int i = 0; i < 100000; i++) {
    v.push_back(i);  // no reallocations
}
```
