# Go Energy Anti-Patterns: Detection & Fix Guide

> Agent skill: scan a Go codebase for energy-wasting patterns and apply fixes.

---

## How to Use This Skill

1. Run the **Detect** command for each anti-pattern against the project source tree.
2. Review each match — not every hit is a true positive; use context.
3. Apply the **Fix** pattern, adapting to the surrounding code.

---

## Profiling Tools

Before pattern-matching, identify actual hotspots with profiling. Optimize what's measured, not what's guessed.

### CPU Profiling

**pprof** (built-in, standard approach):
```bash
# Add to your code for HTTP endpoint:
import _ "net/http/pprof"
go func() { http.ListenAndServe(":6060", nil) }()

# Capture profile:
go tool pprof http://localhost:6060/debug/pprof/profile?seconds=30
# Interactive: top, list <func>, web
```

**Standalone profiling**:
```go
import "runtime/pprof"
f, _ := os.Create("cpu.prof")
pprof.StartCPUProfile(f)
defer pprof.StopCPUProfile()
```

```bash
go tool pprof -http=:8080 cpu.prof
```

### Memory Profiling

**Heap profile**:
```bash
go tool pprof http://localhost:6060/debug/pprof/heap
# Or:
curl http://localhost:6060/debug/pprof/heap > heap.prof
go tool pprof heap.prof
```

**Allocation profiling** (track where allocations happen):
```bash
go tool pprof -alloc_space http://localhost:6060/debug/pprof/heap
```

### Trace Analysis

```bash
curl http://localhost:6060/debug/pprof/trace?seconds=5 > trace.out
go tool trace trace.out
# Opens browser with goroutine analysis, GC events, etc.
```

---

## 1. String Concatenation in Loops

**Why it wastes energy**: Go strings are immutable. Using `+` or `+=` in a loop creates a new string each iteration. Use `strings.Builder` or `bytes.Buffer`.

### Detect

```bash
grep -rEn 'for.*\{' -A15 --include="*.go" ./src | grep -E '\+= *"|= .* \+ "'
grep -rEn 'range.*\{' -A15 --include="*.go" ./src | grep -E '\+= *"|= .* \+ "'
```

### Bad

```go
result := ""
for _, item := range items {
    result += item + ", "
}
```

### Fix

```go
var sb strings.Builder
for _, item := range items {
    sb.WriteString(item)
    sb.WriteString(", ")
}
result := sb.String()

// Or use strings.Join:
result := strings.Join(items, ", ")
```

---

## 2. Not Pre-sizing Slices

**Why it wastes energy**: Slices grow by doubling capacity, causing reallocation and copying. Pre-size when length is known.

### Detect

```bash
grep -rEn 'make\(\[\][^,]+,\s*0\s*\)' --include="*.go" ./src
grep -rEn 'var\s+\w+\s+\[\]\w+\s*$' --include="*.go" ./src
```

### Bad

```go
result := make([]string, 0)
for i := 0; i < 100000; i++ {
    result = append(result, fmt.Sprintf("item%d", i))
}
```

### Fix

```go
result := make([]string, 0, 100000)
for i := 0; i < 100000; i++ {
    result = append(result, fmt.Sprintf("item%d", i))
}
```

---

## 3. Goroutine Leaks

**Why it wastes energy**: Leaked goroutines consume memory and CPU cycles indefinitely.

### Detect

```bash
# Goroutines without context or done channel handling
grep -rEn 'go func\(\)' --include="*.go" ./src | grep -v 'ctx\|done\|cancel\|close'
```

### Bad

```go
func process(ch <-chan int) {
    go func() {
        for v := range ch {  // blocks forever if ch never closes
            handle(v)
        }
    }()
}
```

### Fix

```go
func process(ctx context.Context, ch <-chan int) {
    go func() {
        for {
            select {
            case v, ok := <-ch:
                if !ok { return }
                handle(v)
            case <-ctx.Done():
                return
            }
        }
    }()
}
```

---

## 4. Inefficient Map Iteration

**Why it wastes energy**: Iterating over a map and checking existence with `_, ok := m[k]` inside the loop is O(n) for each lookup.

### Detect

```bash
grep -rEn 'for .* := range' -A10 --include="*.go" ./src | grep -E ', *ok *:= *\w+\['
```

### Bad

```go
for key := range mapA {
    if val, ok := mapB[key]; ok {
        process(key, val)
    }
}
```

### Fix

```go
// If mapA is smaller, iterate over it (already done)
// If mapB is smaller, iterate over mapB instead
for key, val := range mapB {
    if _, ok := mapA[key]; ok {
        process(key, val)
    }
}
```

---

## 5. Defer in Hot Loops

**Why it wastes energy**: `defer` has overhead (~50-100ns). In tight loops, this adds up.

### Detect

```bash
grep -rEn 'for.*\{' -A10 --include="*.go" ./src | grep 'defer '
```

### Bad

```go
for _, file := range files {
    f, _ := os.Open(file)
    defer f.Close()  // defers stack up until function returns
    process(f)
}
```

### Fix

```go
for _, file := range files {
    func() {
        f, _ := os.Open(file)
        defer f.Close()
        process(f)
    }()
}

// Or manage explicitly:
for _, file := range files {
    f, _ := os.Open(file)
    process(f)
    f.Close()
}
```

---

## 6. Unnecessary Allocations with `fmt.Sprintf`

**Why it wastes energy**: `fmt.Sprintf` allocates memory for the result string. For simple conversions, use `strconv`.

### Detect

```bash
grep -rEn 'fmt\.Sprintf\("%d"' --include="*.go" ./src
grep -rEn 'fmt\.Sprintf\("%s"' --include="*.go" ./src
```

### Bad

```go
s := fmt.Sprintf("%d", num)
s := fmt.Sprintf("%s", str)  // pointless
```

### Fix

```go
s := strconv.Itoa(num)
s := str  // just use the string directly
```

---

## 7. Sync.Pool Not Used for Frequent Allocations

**Why it wastes energy**: Repeatedly allocating and discarding objects creates GC pressure. `sync.Pool` recycles objects.

### Detect

```bash
# Look for repeated new() or make() in hot paths
grep -rEn 'for.*\{' -A20 --include="*.go" ./src | grep -E 'new\(|make\(\[\]byte'
```

### Bad

```go
func process(data []byte) {
    buf := make([]byte, 1024)  // allocated every call
    // use buf...
}
```

### Fix

```go
var bufPool = sync.Pool{
    New: func() interface{} {
        return make([]byte, 1024)
    },
}

func process(data []byte) {
    buf := bufPool.Get().([]byte)
    defer bufPool.Put(buf)
    // use buf...
}
```

---

## 8. Reading Entire File into Memory

**Why it wastes energy**: `ioutil.ReadFile` (or `os.ReadFile`) loads entire file into memory. For large files, stream instead.

### Detect

```bash
grep -rEn 'ioutil\.ReadFile|os\.ReadFile' --include="*.go" ./src
```

### Bad

```go
data, _ := os.ReadFile("large.csv")
lines := strings.Split(string(data), "\n")
for _, line := range lines {
    process(line)
}
```

### Fix

```go
f, _ := os.Open("large.csv")
defer f.Close()
scanner := bufio.NewScanner(f)
for scanner.Scan() {
    process(scanner.Text())
}
```
