# Python Energy Anti-Patterns: Detection & Fix Guide

> Agent skill: scan a Python codebase for energy-wasting patterns and apply fixes.

---

## How to Use This Skill

1. Run the **Detect** command for each anti-pattern against the project source tree.
2. Review each match — not every hit is a true positive; use context.
3. Apply the **Fix** pattern, adapting to the surrounding code.

---

## Profiling Tools

Before pattern-matching, identify actual hotspots with profiling. Optimize what's measured, not what's guessed.

### CPU Profiling

**cProfile** (built-in, low overhead):
```bash
python -m cProfile -o profile.prof your_script.py
python -m pstats profile.prof
# In pstats: sort cumtime; stats 20
```

**Note**: cProfile does not support Python's `-c` flag. To profile inline code, use:
```bash
python -c "import cProfile; cProfile.run('your_code_here', sort='cumtime')"
```

**py-spy** (sampling profiler, no code changes, works on running processes):
```bash
pip install py-spy
py-spy top --pid <PID>           # live view
py-spy record -o profile.svg -- python your_script.py  # flamegraph
```

**Scalene** (CPU + memory + energy-aware):
```bash
pip install scalene
scalene your_script.py
# Shows CPU time, memory allocations, and estimated energy by line
```

### Memory Profiling

**memory_profiler**:
```bash
pip install memory_profiler
python -m memory_profiler your_script.py
# Or use @profile decorator on functions
```

**tracemalloc** (built-in):
```python
import tracemalloc
tracemalloc.start()
# ... your code ...
snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')[:10]
```

---

## 1. String Concatenation in Loops

**Why it wastes energy**: Python strings are immutable. `+=` in a loop creates a new string and copies all previous content on every iteration — O(n²) total work.

### Detect

```bash
# String += inside a loop body
grep -rEn '(for|while).*:' -A10 --include="*.py" ./src | grep -E '\+= *["\x27]|= *\w+ *\+ *["\x27]'

# Empty string init followed by loop with +=
grep -rEn '= *["\x27]{2}' -A10 --include="*.py" ./src | grep '\+='

# String concatenation with + inside for loops
grep -rEn 'for .* in .*:' -A5 --include="*.py" ./src | grep -E '= .* \+ '
```

### Bad

```python
result = ""
for item in items:
    result += str(item) + ", "
```

### Fix

```python
result = ", ".join(str(item) for item in items)
```

---

## 2. Loop with `.append()` Instead of List Comprehension

**Why it wastes energy**: List comprehensions run in optimized C internally and are ~2.4x faster than explicit `for` + `.append()` loops.

### Detect

```bash
# Empty list followed by append in loop
grep -rEn '^\s*\w+ *= *\[\]' -A5 --include="*.py" ./src | grep -E '\.append\('

# More precise: empty list, then for, then append (multi-line)
grep -rPzon '\w+ *= *\[\]\s*\n\s*for .* in .*:\s*\n\s*\w+\.append' --include="*.py" ./src
```

### Bad

```python
result = []
for i in range(10000):
    result.append(i * 2)
```

### Fix

```python
result = [i * 2 for i in range(10000)]
```

---

## 3. Using `range(len(...))` Instead of Direct Iteration

**Why it wastes energy**: `range(len(x))` adds an unnecessary index lookup each iteration. Direct iteration or `enumerate()` is cleaner and often faster.

### Detect

```bash
grep -rEn 'for .* in range\(len\(' --include="*.py" ./src
```

### Bad

```python
for i in range(len(items)):
    process(items[i])
```

### Fix

```python
for item in items:
    process(item)

# If you need the index:
for i, item in enumerate(items):
    process(i, item)
```

---

## 4. Repeated String Method Calls in Loops

**Why it wastes energy**: Calling `.upper()`, `.lower()`, `.strip()` on a value that doesn't change between iterations repeats work.

### Detect

```bash
grep -rEn 'for .* in .*:' -A10 --include="*.py" ./src | grep -E '\.(upper|lower|strip|replace)\(\)'
```

### Bad

```python
for name in names:
    if name.lower() == search_term.lower():  # search_term.lower() every iteration
        matches.append(name)
```

### Fix

```python
search_lower = search_term.lower()
for name in names:
    if name.lower() == search_lower:
        matches.append(name)
```

---

## 5. Linear Search in a List (O(n)) When a Set Would Give O(1)

**Why it wastes energy**: `if x in some_list` is O(n). For repeated membership checks, converting to a `set` drops this to O(1).

### Detect

```bash
# 'in list_var' inside a loop
grep -rEn 'for .* in .*:' -A5 --include="*.py" ./src | grep -E 'if .* in \w+:'

# Nested for loops (potential O(n²))
grep -rEn 'for .* in .*:' -A10 --include="*.py" ./src | grep -E '^\s+for .* in .*:'
```

### Bad

```python
common = []
for item in list1:
    if item in list2:  # O(n) lookup each time
        common.append(item)
```

### Fix

```python
set2 = set(list2)
common = [item for item in list1 if item in set2]
```

---

## 6. Invariant Computation Inside Loops

**Why it wastes energy**: Expressions whose result never changes are re-evaluated every iteration.

### Detect

```bash
# Heavy math/numpy operations inside loops
grep -rEn 'for .* in .*:' -A10 --include="*.py" ./src | grep -E '(math\.|np\.|numpy\.)(sqrt|power|sin|cos|log|exp)'

# re.compile inside loops
grep -rEn '(for|while)' -A10 --include="*.py" ./src | grep -E 're\.compile\('
```

### Bad

```python
for i in range(n):
    factor = math.sqrt(base_value) * math.pi
    result[i] = data[i] * factor
```

### Fix

```python
factor = math.sqrt(base_value) * math.pi
for i in range(n):
    result[i] = data[i] * factor
```

---

## 7. Object Instantiation in Loops

**Why it wastes energy**: Creating heavy objects (regex patterns, formatters, connections) inside a loop that could be created once.

### Detect

```bash
grep -rEn 'for .* in .*:' -A10 --include="*.py" ./src | grep -E '= *[A-Z][a-zA-Z]+\('
```

### Bad

```python
for line in lines:
    pattern = re.compile(r'\d+')
    matches = pattern.findall(line)
```

### Fix

```python
pattern = re.compile(r'\d+')
for line in lines:
    matches = pattern.findall(line)
```

---

## 8. `open()` Without Context Manager (`with`)

**Why it wastes energy**: Without `with`, file handles may not be closed if an exception occurs, leaking OS resources.

### Detect

```bash
# open() not preceded by 'with'
grep -rEn "^\s*\w+ *= *open\(" --include="*.py" ./src | grep -v 'with'

# All open() calls (review each)
grep -rEn '= *open\(' --include="*.py" ./src
```

### Bad

```python
f = open("data.txt", "r")
content = f.read()
# if an exception occurs, f is never closed
f.close()
```

### Fix

```python
with open("data.txt", "r") as f:
    content = f.read()
# automatically closed
```

---

## 9. Recursive Function Without Memoization

**Why it wastes energy**: Naive recursion recalculates the same sub-problems exponentially many times.

### Detect

```bash
# Recursive functions without @lru_cache or @cache
grep -rEn 'def \w+\(.*\):' -B2 -A5 --include="*.py" ./src | grep -E 'return.*\w+\(' | grep -v '@.*cache'

# Fibonacci / factorial patterns specifically
grep -rEin 'def (fib|fibonacci|fac|factorial)' --include="*.py" ./src
```

### Bad

```python
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)  # exponential time
```

### Fix

```python
from functools import lru_cache

@lru_cache(maxsize=None)
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)  # O(n) with memoization
```

---

## 10. N+1 Query Problem (Django / SQLAlchemy)

**Why it wastes energy**: An initial query fetches N rows, then N additional queries fetch related objects one at a time.

### Detect

```bash
# Django: queryset access in loop without select_related/prefetch_related
grep -rEn '\.objects\.(all|filter)\(' -A10 --include="*.py" ./src | grep -E 'for .* in'

# Missing select_related / prefetch_related
grep -rEn '\.objects\.(all|filter|get)\(' --include="*.py" ./src | grep -v -E '(select_related|prefetch_related)'

# SQLAlchemy: query followed by loop
grep -rEn 'session\.query\(' -A10 --include="*.py" ./src | grep -E 'for .* in'
```

### Bad (Django)

```python
users = User.objects.all()
for user in users:
    print(user.profile.bio)  # N extra queries
```

### Fix (Django)

```python
users = User.objects.select_related('profile').all()
for user in users:
    print(user.profile.bio)  # single JOIN query
```

---

## 11. Database Queries Inside Loops

**Why it wastes energy**: Each query has network round-trip overhead. Batch operations amortize this.

### Detect

```bash
grep -rEn 'for .* in .*:' -A10 --include="*.py" ./src | grep -E '(cursor\.|\.execute\(|\.query\(|session\.)'
```

### Bad

```python
for user_id in user_ids:
    user = session.query(User).get(user_id)
    process(user)
```

### Fix

```python
users = session.query(User).filter(User.id.in_(user_ids)).all()
for user in users:
    process(user)
```

---

## 12. `math.pow()` Instead of `**` Operator

**Why it wastes energy**: `math.pow()` has function-call overhead and converts to float. The `**` operator is a bytecode instruction and faster.

### Detect

```bash
grep -rEn 'math\.pow\(' --include="*.py" ./src
```

### Bad

```python
result = math.pow(x, 2)
```

### Fix

```python
result = x ** 2
```

---

## 13. Returning a List When a Generator Would Suffice

**Why it wastes energy**: A list materializes all elements in memory at once. A generator yields one at a time, saving memory for large sequences.

### Detect

```bash
grep -rEn 'return \[.* for .* in' --include="*.py" ./src
```

### Bad

```python
def get_squares(n):
    return [x ** 2 for x in range(n)]  # entire list in memory
```

### Fix

```python
def get_squares(n):
    return (x ** 2 for x in range(n))  # generator, lazy evaluation

# Or use yield:
def get_squares(n):
    for x in range(n):
        yield x ** 2
```

---

## 14. Global Variable Access in Hot Loops

**Why it wastes energy**: Python looks up global variables via dictionary lookup (LOAD_GLOBAL), which is slower than local variable access (LOAD_FAST).

### Detect

```bash
# Find module-level variable assignments
grep -rEn '^[a-z_]+ *=' --include="*.py" ./src

# Then check if those names appear inside loops in the same file
```

### Bad

```python
MULTIPLIER = 2.5

def process(data):
    result = []
    for item in data:
        result.append(item * MULTIPLIER)  # global lookup each iteration
    return result
```

### Fix

```python
MULTIPLIER = 2.5

def process(data, multiplier=MULTIPLIER):
    result = []
    for item in data:
        result.append(item * multiplier)  # local lookup (faster)
    return result

# Or assign to local variable:
def process(data):
    multiplier = MULTIPLIER
    return [item * multiplier for item in data]
```

---

## 15. SELECT * in Queries

**Why it wastes energy**: Fetches columns you don't need, wasting bandwidth, memory, and deserialization cost.

### Detect

```bash
grep -rEin 'SELECT \*' --include="*.py" ./src
grep -rEin "'\s*SELECT \*" --include="*.py" ./src
```

### Fix

Select only the columns you need:

```python
# Bad
cursor.execute("SELECT * FROM users WHERE active = 1")

# Good
cursor.execute("SELECT id, name, email FROM users WHERE active = 1")
```

---

## 16. Blocking I/O Inside `async` Functions

**Why it wastes energy**: Blocking calls in async code block the entire event loop, negating concurrency benefits and wasting time/energy waiting.

### Detect

```bash
grep -rEn 'async def' -A20 --include="*.py" ./src | grep -E '(open\(|requests\.|urllib)'
```

### Bad

```python
async def fetch_data():
    response = requests.get("https://api.example.com/data")  # blocks event loop
    return response.json()
```

### Fix

```python
import aiohttp

async def fetch_data():
    async with aiohttp.ClientSession() as session:
        async with session.get("https://api.example.com/data") as response:
            return await response.json()
```

---

## 17. Missing HTTP Response Compression

**Why it wastes energy**: Serving uncompressed HTTP responses wastes network bandwidth and energy at every hop. Compression middleware reduces payload size by 60-80%.

### Detect

```bash
# Django without GZipMiddleware
grep -rEn "MIDDLEWARE" -A20 --include="*.py" ./src | grep -v "GZipMiddleware" | grep "MIDDLEWARE"
grep -rL "GZipMiddleware" --include="*.py" ./src | xargs grep -l "MIDDLEWARE"

# Flask without compress
grep -rL "compress\|Compress" --include="*.py" ./src | xargs grep -l "Flask\(__name__"

# FastAPI without GZipMiddleware
grep -rL "GZipMiddleware" --include="*.py" ./src | xargs grep -l "FastAPI\(\)"
```

### Bad

```python
# Django settings.py
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # No compression — responses sent at full size
]
```

### Fix

```python
# Django settings.py
MIDDLEWARE = [
    "django.middleware.gzip.GZipMiddleware",  # add as first middleware
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
]

# Flask
from flask_compress import Compress
app = Flask(__name__)
Compress(app)

# FastAPI
from starlette.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=500)
```

---

## 18. Verbose Serialization Format (JSON Where Binary Would Be More Efficient)

**Why it wastes energy**: JSON and XML are human-readable but verbose. For internal service-to-service communication, binary formats like Protobuf or MessagePack are 2-10x smaller and faster to parse, reducing both network and CPU energy.

### Detect

```bash
# JSON serialization in internal service communication
grep -rEn 'json\.dumps\(|json\.loads\(' --include="*.py" ./src

# Large JSON responses from internal APIs
grep -rEn 'jsonify\(|JSONResponse\(|JsonResponse\(' --include="*.py" ./src

# XML serialization
grep -rEn 'xml\.etree\|lxml\|xmltodict' --include="*.py" ./src

# Missing protobuf/msgpack usage
grep -rL 'protobuf\|msgpack\|avro' --include="*.py" ./src | xargs grep -l 'json\.dumps'
```

### Bad

```python
# Internal service call using JSON (verbose, slow to parse)
import json, requests

def get_user_orders(user_id):
    response = requests.get(f"http://orders-service/api/{user_id}")
    return json.loads(response.content)  # ~500 bytes per order as JSON
```

### Fix

```python
# Use MessagePack for internal service communication (~60% smaller)
import msgpack, requests

def get_user_orders(user_id):
    response = requests.get(
        f"http://orders-service/api/{user_id}",
        headers={"Accept": "application/msgpack"}
    )
    return msgpack.unpackb(response.content)  # ~200 bytes per order

# Or use Protobuf for strongly-typed contracts:
# Define .proto schema, generate Python stubs, use for internal APIs
```

**Note**: JSON is the right choice for public-facing APIs and browser clients. Reserve binary formats for internal service-to-service communication where both sides are controlled.
