# Code-Level Energy Anti-Patterns: Detection & Optimization Guide

> Granular code patterns that waste energy, with grep/regex patterns to find them in your codebase

---

## Table of Contents

1. [Overview](#overview)
2. [String Operations](#1-string-operations)
3. [Loop Inefficiencies](#2-loop-inefficiencies)
4. [Memory Management](#3-memory-management)
5. [Database & Query Patterns](#4-database--query-patterns)
6. [Algorithm Inefficiencies](#5-algorithm-inefficiencies)
7. [Object Creation & Allocation](#6-object-creation--allocation)
8. [I/O Operations](#7-io-operations)
9. [Collection & Data Structure Misuse](#8-collection--data-structure-misuse)
10. [Language-Specific Anti-Patterns](#9-language-specific-anti-patterns)
11. [Detection Tools](#detection-tools)
12. [Sources](#sources)

---

## Overview

Each anti-pattern in this document includes:
- **Description**: What the problem is and why it wastes energy
- **Bad Example**: Code demonstrating the anti-pattern
- **Good Example**: The optimized alternative
- **Energy Impact**: How this affects CPU, memory, and power consumption
- **Grep Patterns**: Regular expressions to detect the anti-pattern in your codebase

### Using the Grep Patterns

```bash
# Basic usage
grep -rn "PATTERN" --include="*.java" ./src

# Extended regex
grep -rEn "PATTERN" --include="*.py" ./src

# With context (3 lines before/after)
grep -rEn -B3 -A3 "PATTERN" ./src
```

---

## 1. String Operations

### 1.1 String Concatenation in Loops

**Description**: Concatenating strings with `+` or `+=` inside loops creates a new string object on each iteration. Strings are immutable in most languages, so each concatenation copies all previous content plus the new content.

**Bad Example (Java)**:
```java
String result = "";
for (int i = 0; i < 10000; i++) {
    result += "item" + i + ", ";  // Creates new String each iteration
}
```

**Good Example (Java)**:
```java
StringBuilder sb = new StringBuilder();
for (int i = 0; i < 10000; i++) {
    sb.append("item").append(i).append(", ");
}
String result = sb.toString();
```

**Energy Impact**: 
- Time complexity goes from O(n) to O(n²) with naive concatenation
- Each iteration allocates new memory, triggers more GC cycles
- 10,000 iterations can be 100x slower than StringBuilder approach

**Grep Patterns**:

```bash
# Java: String concatenation with += in potential loop context
grep -rEn '\+= *"' --include="*.java" ./src
grep -rEn 'String.*= *"";' --include="*.java" ./src
grep -rEn 'for.*\{[^}]*\+=' --include="*.java" ./src

# Java: String + operator near loop keywords
grep -rEn '(for|while).*\{' -A20 --include="*.java" ./src | grep -E '\+ *"|\+= *"'

# C#: Same pattern
grep -rEn 'string.*\+=' --include="*.cs" ./src
grep -rEn '\+= *"' --include="*.cs" ./src

# Python: String concatenation in loops
grep -rEn '(for|while).*:' -A10 --include="*.py" ./src | grep -E '\+= *["\x27]|= *\w+ *\+ *["\x27]'

# JavaScript/TypeScript
grep -rEn 'let.*= *["\x27]{2}' --include="*.js" --include="*.ts" ./src
grep -rEn '\+= *[`"\x27]' --include="*.js" --include="*.ts" ./src
```

**Python-Specific Detection**:
```bash
# Python: Detect string join anti-pattern
grep -rEn 'for .* in .*:' -A5 --include="*.py" ./src | grep -E '= .* \+ '

# Should use: ''.join(list) instead
```

---

### 1.2 Repeated String Method Calls in Loops

**Description**: Calling methods like `.toUpperCase()`, `.toLowerCase()`, `.trim()` on the same string repeatedly in a loop.

**Bad Example (Java)**:
```java
for (Item item : items) {
    if (item.getName().toUpperCase().equals(searchTerm.toUpperCase())) {
        // searchTerm.toUpperCase() called every iteration!
    }
}
```

**Good Example**:
```java
String searchTermUpper = searchTerm.toUpperCase();
for (Item item : items) {
    if (item.getName().toUpperCase().equals(searchTermUpper)) {
        // Computed once outside loop
    }
}
```

**Grep Patterns**:
```bash
# Java: Method calls on same variable inside loops
grep -rEn '(for|while).*\{' -A30 --include="*.java" ./src | grep -E '\.(toUpperCase|toLowerCase|trim|substring)\(\)'

# Python: Repeated string operations
grep -rEn 'for .* in .*:' -A10 --include="*.py" ./src | grep -E '\.(upper|lower|strip|replace)\(\)'

# JavaScript
grep -rEn '(for|while|forEach)' -A10 --include="*.js" ./src | grep -E '\.(toUpperCase|toLowerCase|trim|split)\(\)'
```

---

## 2. Loop Inefficiencies

### 2.1 Recalculating Length/Size Inside Loop Condition

**Description**: Calling `.length`, `.size()`, or `len()` in every loop iteration when the collection doesn't change.

**Bad Example (Java)**:
```java
for (int i = 0; i < list.size(); i++) {  // size() called every iteration
    process(list.get(i));
}
```

**Good Example**:
```java
int size = list.size();
for (int i = 0; i < size; i++) {
    process(list.get(i));
}
// Or better: use enhanced for-loop
for (Item item : list) {
    process(item);
}
```

**Grep Patterns**:
```bash
# Java: .size() or .length in loop condition
grep -rEn 'for *\(.*;.*\.(size|length)\(\)' --include="*.java" ./src
grep -rEn 'while *\(.*\.(size|length)\(\)' --include="*.java" ./src

# JavaScript: .length in loop
grep -rEn 'for *\(.*;.*\.length' --include="*.js" --include="*.ts" ./src

# Python: len() in loop (less critical due to O(1) but still a pattern)
grep -rEn 'for .* in range\(len\(' --include="*.py" ./src

# C/C++: strlen in loop (very expensive - O(n) per call!)
grep -rEn 'for *\(.*;.*strlen\(' --include="*.c" --include="*.cpp" ./src
grep -rEn 'while *\(.*strlen\(' --include="*.c" --include="*.cpp" ./src
```

---

### 2.2 Nested Loops with O(n²) or Worse When O(n) Possible

**Description**: Using nested loops for lookups/comparisons when a Set or HashMap would provide O(1) lookup.

**Bad Example (Python)**:
```python
# O(n*m) - checking if item exists in list
common = []
for item in list1:
    if item in list2:  # O(n) lookup each time!
        common.append(item)
```

**Good Example**:
```python
# O(n+m) - using set for O(1) lookup
set2 = set(list2)
common = [item for item in list1 if item in set2]
# Or: common = list(set(list1) & set(list2))
```

**Energy Impact**: For two lists of 10,000 items each:
- Bad: 100,000,000 comparisons
- Good: ~20,000 operations
- **498x speedup** measured in benchmarks

**Grep Patterns**:
```bash
# Python: 'in list' inside loop (potential O(n²))
grep -rEn 'for .* in .*:' -A5 --include="*.py" ./src | grep -E 'if .* in \w+:'

# Python: Nested for loops
grep -rEn 'for .* in .*:' -A10 --include="*.py" ./src | grep -E '^\s+for .* in .*:'

# Java: Nested loops with contains()
grep -rEn 'for.*\{' -A15 --include="*.java" ./src | grep -E '\.contains\('

# JavaScript: includes() in loop
grep -rEn '(for|while|forEach)' -A10 --include="*.js" ./src | grep -E '\.includes\('
```

---

### 2.3 Invariant Computation Inside Loops

**Description**: Computing values inside a loop that don't change between iterations.

**Bad Example**:
```java
for (int i = 0; i < n; i++) {
    double factor = Math.sqrt(baseValue) * Math.PI;  // Same every iteration!
    result[i] = data[i] * factor;
}
```

**Good Example**:
```java
double factor = Math.sqrt(baseValue) * Math.PI;  // Computed once
for (int i = 0; i < n; i++) {
    result[i] = data[i] * factor;
}
```

**Grep Patterns**:
```bash
# Java: Math operations inside loops
grep -rEn 'for.*\{' -A20 --include="*.java" ./src | grep -E 'Math\.(sqrt|pow|sin|cos|log|exp)\('

# Python: Heavy operations in loops
grep -rEn 'for .* in .*:' -A10 --include="*.py" ./src | grep -E '(math\.|np\.|numpy\.)(sqrt|power|sin|cos|log|exp)'

# Any language: Regex compilation inside loops
grep -rEn '(for|while)' -A10 --include="*.java" ./src | grep -E 'Pattern\.compile\('
grep -rEn '(for|while)' -A10 --include="*.py" ./src | grep -E 're\.compile\('
```

---

### 2.4 Using append() Instead of List Comprehension (Python)

**Description**: In Python, list comprehensions are faster than explicit loops with `.append()`.

**Bad Example**:
```python
result = []
for i in range(10000):
    result.append(i * 2)
```

**Good Example**:
```python
result = [i * 2 for i in range(10000)]
```

**Energy Impact**: List comprehensions can be **2.4x faster** due to optimized C implementation.

**Grep Patterns**:
```bash
# Python: Loop with append that could be list comprehension
grep -rEn '^\s*\w+ *= *\[\]' -A5 --include="*.py" ./src | grep -E '\.append\('

# More specific: empty list followed by for loop with append
grep -rPzon '\w+ *= *\[\]\s*\n\s*for .* in .*:\s*\n\s*\w+\.append' --include="*.py" ./src
```

---

## 3. Memory Management

### 3.1 Creating Objects Inside Loops

**Description**: Instantiating objects inside loops when they could be reused or created once outside.

**Bad Example (Java)**:
```java
for (int i = 0; i < 1000; i++) {
    SimpleDateFormat sdf = new SimpleDateFormat("yyyy-MM-dd");  // New object each time!
    String date = sdf.format(dates[i]);
}
```

**Good Example**:
```java
SimpleDateFormat sdf = new SimpleDateFormat("yyyy-MM-dd");
for (int i = 0; i < 1000; i++) {
    String date = sdf.format(dates[i]);
}
```

**Grep Patterns**:
```bash
# Java: new Object() inside loops
grep -rEn '(for|while).*\{' -A20 --include="*.java" ./src | grep -E 'new [A-Z][a-zA-Z]+\('

# Specific expensive objects
grep -rEn '(for|while)' -A15 --include="*.java" ./src | grep -E 'new (SimpleDateFormat|DecimalFormat|Pattern|StringBuilder|ArrayList|HashMap)\('

# Python: Object instantiation in loops
grep -rEn 'for .* in .*:' -A10 --include="*.py" ./src | grep -E '= *[A-Z][a-zA-Z]+\('
```

---

### 3.2 Not Closing Resources / Missing try-with-resources

**Description**: Not properly closing file handles, database connections, streams, causing resource leaks.

**Bad Example (Java)**:
```java
FileInputStream fis = new FileInputStream("file.txt");
// Use fis...
// Forgot to close! Or exception prevents close
```

**Good Example**:
```java
try (FileInputStream fis = new FileInputStream("file.txt")) {
    // Use fis...
}  // Automatically closed
```

**Grep Patterns**:
```bash
# Java: new Stream/Reader/Writer without try-with-resources
grep -rEn 'new (File|Buffered|Input|Output)(Stream|Reader|Writer)\(' --include="*.java" ./src | grep -v 'try *('

# Java: JDBC connections without try-with-resources
grep -rEn '(getConnection|createStatement|prepareStatement)\(' --include="*.java" ./src

# Python: open() without 'with'
grep -rEn "^\s*\w+ *= *open\(" --include="*.py" ./src | grep -v 'with'

# Python: Should be using context manager
grep -rEn '= *open\(' --include="*.py" ./src
```

---

### 3.3 Holding References Longer Than Needed

**Description**: Keeping references to large objects when they're no longer needed, preventing garbage collection.

**Bad Example**:
```java
public class DataProcessor {
    private List<byte[]> processedData;  // Held for entire object lifetime
    
    public void process(byte[] input) {
        byte[] result = heavyProcessing(input);
        processedData.add(result);  // Growing forever!
    }
}
```

**Grep Patterns**:
```bash
# Java: Static collections (often hold references too long)
grep -rEn 'static.*(List|Map|Set|Collection).*=' --include="*.java" ./src

# Java: Instance-level collections that might grow unbounded
grep -rEn 'private.*(List|Map|Set)<.*> *\w+ *= *new' --include="*.java" ./src
```

---

## 4. Database & Query Patterns

### 4.1 N+1 Query Problem

**Description**: Executing N additional queries for N records fetched by an initial query, instead of fetching all data in one query.

**Bad Example (Python/Django)**:
```python
users = User.objects.all()  # 1 query
for user in users:
    print(user.profile.bio)  # N queries! One per user
```

**Good Example**:
```python
users = User.objects.select_related('profile').all()  # 1 query with JOIN
for user in users:
    print(user.profile.bio)  # No additional queries
```

**Grep Patterns**:
```bash
# Python/Django: Potential N+1 (loop over queryset accessing related)
grep -rEn '\.objects\.(all|filter)\(' -A10 --include="*.py" ./src | grep -E 'for .* in'

# Django: Missing select_related or prefetch_related
grep -rEn '\.objects\.(all|filter|get)\(' --include="*.py" ./src | grep -v -E '(select_related|prefetch_related)'

# SQLAlchemy: Potential N+1
grep -rEn 'session\.query\(' -A10 --include="*.py" ./src | grep -E 'for .* in'

# Java/JPA: Lazy loading in loops
grep -rEn 'for.*:.*\{' -A10 --include="*.java" ./src | grep -E '\.(get|find)[A-Z]\w*\(\)'

# Rails: Potential N+1
grep -rEn '\.(all|where|find)\b' -A5 --include="*.rb" ./src | grep -E '\.each'
```

---

### 4.2 SELECT * Queries

**Description**: Selecting all columns when only specific ones are needed wastes memory, bandwidth, and processing.

**Bad Example**:
```sql
SELECT * FROM users WHERE status = 'active';
```

**Good Example**:
```sql
SELECT id, name, email FROM users WHERE status = 'active';
```

**Grep Patterns**:
```bash
# SQL: SELECT * pattern
grep -rEin 'SELECT \*' --include="*.sql" --include="*.java" --include="*.py" --include="*.php" ./src

# In code strings
grep -rEin '"SELECT \*|'\''SELECT \*' --include="*.java" --include="*.py" --include="*.js" ./src

# ORM patterns that fetch all columns
grep -rEn '\.findAll\(|\.getAll\(|\.fetchAll\(' --include="*.java" --include="*.js" ./src
```

---

### 4.3 Queries Inside Loops

**Description**: Executing database queries inside loops instead of batching.

**Bad Example**:
```java
for (Long id : userIds) {
    User user = userRepository.findById(id);  // Query per ID!
    process(user);
}
```

**Good Example**:
```java
List<User> users = userRepository.findAllById(userIds);  // Single query
for (User user : users) {
    process(user);
}
```

**Grep Patterns**:
```bash
# Java: Repository/DAO calls inside loops
grep -rEn '(for|while).*\{' -A15 --include="*.java" ./src | grep -E '\.(find|get|fetch|load|query|select|execute)\w*\('

# Python: DB operations in loops  
grep -rEn 'for .* in .*:' -A10 --include="*.py" ./src | grep -E '(cursor\.|\.execute\(|\.query\(|session\.)'

# JavaScript/Node: DB calls in loops
grep -rEn '(for|while|forEach)' -A10 --include="*.js" ./src | grep -E '(\.find\(|\.findOne\(|\.query\(|await.*Model\.)'
```

---

### 4.4 Missing Database Indexes

**Detection Note**: This requires checking SQL schema files or using database tools, not just grep.

**Grep Patterns for Schema Files**:
```bash
# Find WHERE clauses to identify columns needing indexes
grep -rEin 'WHERE\s+\w+\s*=' --include="*.sql" ./src

# Find JOIN conditions
grep -rEin 'JOIN.*ON\s+\w+\.\w+\s*=' --include="*.sql" ./src

# Find ORDER BY columns (often need indexes)
grep -rEin 'ORDER BY \w+' --include="*.sql" ./src

# Check for existing indexes
grep -rEin 'CREATE INDEX|CREATE UNIQUE INDEX' --include="*.sql" ./src
```

---

## 5. Algorithm Inefficiencies

### 5.1 Naive Recursion Without Memoization

**Description**: Recursive functions that recalculate the same values multiple times.

**Bad Example (Python)**:
```python
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)  # Exponential time!
```

**Good Example**:
```python
from functools import lru_cache

@lru_cache(maxsize=None)
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)  # O(n) with caching
```

**Energy Impact**: `fibonacci(35)` - naive takes seconds, memoized takes microseconds.

**Grep Patterns**:
```bash
# Python: Recursive function without @lru_cache or @cache
grep -rEn 'def \w+\(.*\):' -B2 -A5 --include="*.py" ./src | grep -E 'return.*\w+\(' | grep -v '@.*cache'

# Find recursive calls (function calls itself)
grep -rPzon 'def (\w+)\([^)]*\):[^}]+\1\(' --include="*.py" ./src

# Java: Recursive methods (manual check needed)
grep -rEn 'return.*\w+\(' --include="*.java" ./src | grep -v 'this\.'

# Look for fibonacci-like patterns specifically
grep -rEin 'def (fib|fibonacci|fac|factorial)' --include="*.py" ./src
grep -rEin '(fib|fibonacci|factorial)\s*\(' --include="*.java" ./src
```

---

### 5.2 Using O(n²) Sort When O(n log n) Available

**Description**: Implementing bubble sort, insertion sort, or selection sort for large datasets.

**Grep Patterns**:
```bash
# Detect potential bubble/selection sort patterns (nested loops with swap)
grep -rEn 'for.*:' -A20 --include="*.py" ./src | grep -E 'for.*:' | head -20

# Look for manual sorting implementations
grep -rEin '(bubble|selection|insertion).*sort' --include="*.py" --include="*.java" --include="*.js" ./src

# Swap patterns that might indicate manual sorting
grep -rEn '\w+, *\w+ *= *\w+, *\w+' --include="*.py" ./src  # Python swap
grep -rEn 'temp *= *\w+\[' --include="*.java" --include="*.js" ./src  # temp variable swap
```

---

### 5.3 Linear Search When Binary Search Possible

**Description**: Using linear search O(n) on sorted data when binary search O(log n) would work.

**Grep Patterns**:
```bash
# Python: 'in list' on what might be sorted data
grep -rEn '\.sort\(\)' -A20 --include="*.py" ./src | grep -E 'if .* in \w+:'

# Manual linear search pattern
grep -rEn 'for .* in .*:' -A5 --include="*.py" ./src | grep -E 'if .* == '

# Java: Manual iteration when Collections.binarySearch could work
grep -rEn 'Collections\.sort\(' -A20 --include="*.java" ./src | grep -E 'for.*\{.*if.*=='
```

---

## 6. Object Creation & Allocation

### 6.1 Autoboxing in Loops

**Description**: Automatic conversion between primitives and wrapper objects in loops creates unnecessary objects.

**Bad Example (Java)**:
```java
Long sum = 0L;
for (int i = 0; i < 1000000; i++) {
    sum += i;  // Creates new Long object each iteration!
}
```

**Good Example**:
```java
long sum = 0L;  // primitive
for (int i = 0; i < 1000000; i++) {
    sum += i;  // No object creation
}
```

**Grep Patterns**:
```bash
# Java: Wrapper types in accumulator patterns
grep -rEn '(Integer|Long|Double|Float|Boolean) \w+ *= *[0-9]' --include="*.java" ./src

# Wrapper types with += or similar operations
grep -rEn '(Integer|Long|Double|Float) \w+' -A10 --include="*.java" ./src | grep -E '\+= *'

# Using wrapper types in for loops
grep -rEn 'for *\( *(Integer|Long|Double|Float)' --include="*.java" ./src
```

---

### 6.2 Varargs Creating Unnecessary Arrays

**Description**: Each varargs call creates a new array object.

**Bad Example**:
```java
for (int i = 0; i < 10000; i++) {
    logger.debug("Processing item: {}", i);  // Creates Object[] each call
}
```

**Good Example**:
```java
if (logger.isDebugEnabled()) {  // Check first
    for (int i = 0; i < 10000; i++) {
        logger.debug("Processing item: {}", i);
    }
}
```

**Grep Patterns**:
```bash
# Java: Logging inside loops without guard
grep -rEn '(for|while).*\{' -A20 --include="*.java" ./src | grep -E '(logger|LOG|log)\.(debug|trace|info)\('

# Check for missing isDebugEnabled guards
grep -rEn 'log.*\.debug\(' --include="*.java" ./src | grep -v 'isDebugEnabled'
```

---

## 7. I/O Operations

### 7.1 Unbuffered I/O

**Description**: Reading/writing files byte-by-byte or line-by-line without buffering.

**Bad Example (Java)**:
```java
FileInputStream fis = new FileInputStream("file.txt");
int b;
while ((b = fis.read()) != -1) {  // One system call per byte!
    process(b);
}
```

**Good Example**:
```java
BufferedInputStream bis = new BufferedInputStream(new FileInputStream("file.txt"));
int b;
while ((b = bis.read()) != -1) {  // Reads chunks, returns from buffer
    process(b);
}
```

**Grep Patterns**:
```bash
# Java: FileInputStream/FileOutputStream without Buffered wrapper
grep -rEn 'new File(Input|Output)Stream\(' --include="*.java" ./src | grep -v 'Buffered'

# Java: FileReader/FileWriter without Buffered
grep -rEn 'new File(Reader|Writer)\(' --include="*.java" ./src | grep -v 'Buffered'

# Python: Reading entire file into memory
grep -rEn '\.read\(\)' --include="*.py" ./src | grep -v 'readline\|read\([0-9]'
```

---

### 7.2 Synchronous I/O in Hot Paths

**Description**: Blocking I/O operations in performance-critical code paths.

**Grep Patterns**:
```bash
# Java: Synchronous file operations (consider async alternatives)
grep -rEn '\.(read|write)\(' --include="*.java" ./src

# Node.js: Sync methods (should use async versions)
grep -rEn '(readFileSync|writeFileSync|existsSync|mkdirSync|readdirSync)' --include="*.js" --include="*.ts" ./src

# Python: Blocking I/O in async functions
grep -rEn 'async def' -A20 --include="*.py" ./src | grep -E '(open\(|requests\.|urllib)'
```

---

## 8. Collection & Data Structure Misuse

### 8.1 Wrong Collection Type for Use Case

| Operation | ArrayList | LinkedList | HashSet | TreeSet |
|-----------|-----------|------------|---------|---------|
| Random access | O(1) ✓ | O(n) ✗ | N/A | N/A |
| Insert at beginning | O(n) ✗ | O(1) ✓ | N/A | N/A |
| Contains check | O(n) ✗ | O(n) ✗ | O(1) ✓ | O(log n) |
| Sorted iteration | O(n log n) | O(n log n) | N/A | O(n) ✓ |

**Grep Patterns**:
```bash
# Java: LinkedList with get(index) - O(n) each time!
grep -rEn 'LinkedList' -A20 --include="*.java" ./src | grep -E '\.get\([0-9i]'

# Java: ArrayList for frequent beginning insertions
grep -rEn 'ArrayList' -A20 --include="*.java" ./src | grep -E '\.add\(0,'

# Java: List.contains() when Set would be better
grep -rEn '(ArrayList|LinkedList)' -A30 --include="*.java" ./src | grep -E '\.contains\('

# Python: List for membership testing (should be set)
grep -rEn '\[\]' -A10 --include="*.py" ./src | grep -E 'if .* in \w+:'
```

---

### 8.2 Not Pre-sizing Collections

**Description**: Collections that grow dynamically reallocate and copy data multiple times.

**Bad Example**:
```java
List<String> list = new ArrayList<>();  // Default capacity 10
for (int i = 0; i < 100000; i++) {
    list.add("item" + i);  // Multiple resizes and copies
}
```

**Good Example**:
```java
List<String> list = new ArrayList<>(100000);  // Pre-sized
for (int i = 0; i < 100000; i++) {
    list.add("item" + i);  // No resizing needed
}
```

**Grep Patterns**:
```bash
# Java: ArrayList/HashMap created without initial capacity near loops
grep -rEn 'new (ArrayList|HashMap|HashSet|StringBuilder)\(\)' --include="*.java" ./src

# Look for patterns where we know the size
grep -rEn '\w+\.size\(\)' -B5 --include="*.java" ./src | grep 'new ArrayList\(\)'
```

---

### 8.3 Using ArrayList When Array Would Suffice

**Description**: For fixed-size collections, plain arrays are more memory-efficient and faster.

**Grep Patterns**:
```bash
# Java: ArrayList that never grows (potential array candidate)
grep -rEn 'new ArrayList<>\([0-9]+\)' --include="*.java" ./src

# Fixed-size collections initialized with Arrays.asList
grep -rEn 'Arrays\.asList\(' --include="*.java" ./src
```

---

## 9. Language-Specific Anti-Patterns

### 9.1 Python-Specific

```bash
# Global variable access in loops (slower than local)
grep -rEn '^[a-z_]+ *=' ./src/*.py  # Find globals
grep -rEn 'for .* in .*:' -A10 --include="*.py" ./src | grep -v 'def '  # Check usage in loops

# Using + for string concatenation instead of join()
grep -rEn '= *["\x27]{2}' -A10 --include="*.py" ./src | grep '\+='

# Using ** instead of pow() in hot paths (** is actually faster, but both patterns exist)
grep -rEn 'math\.pow\(' --include="*.py" ./src

# Not using generators for large sequences
grep -rEn 'return \[.* for .* in' --include="*.py" ./src  # Could be generator
```

### 9.2 JavaScript-Specific

```bash
# forEach when for...of would be more efficient
grep -rEn '\.forEach\(' --include="*.js" --include="*.ts" ./src

# Array spread in loops
grep -rEn '(for|while)' -A10 --include="*.js" ./src | grep -E '\.\.\.'

# Creating functions inside loops
grep -rEn '(for|while)' -A10 --include="*.js" ./src | grep -E '(function|=>)'

# Inefficient array methods chaining
grep -rEn '\.filter\(.*\.map\(' --include="*.js" ./src
grep -rEn '\.map\(.*\.filter\(' --include="*.js" ./src
```

### 9.3 Java-Specific

```bash
# String.format in tight loops (slow)
grep -rEn '(for|while)' -A15 --include="*.java" ./src | grep 'String\.format\('

# Reflection in loops
grep -rEn '(for|while)' -A15 --include="*.java" ./src | grep -E '\.(getMethod|getField|invoke)\('

# Synchronized blocks in loops
grep -rEn '(for|while)' -A15 --include="*.java" ./src | grep 'synchronized'

# Creating new threads in loops (use thread pool!)
grep -rEn '(for|while)' -A15 --include="*.java" ./src | grep 'new Thread\('
```

---

## Detection Tools

### Static Analysis Tools

| Tool | Languages | Purpose |
|------|-----------|---------|
| **SonarQube** | Multi-language | Code quality, performance issues |
| **SpotBugs** | Java | Bug patterns, performance issues |
| **PMD** | Java, JS, etc. | Anti-pattern detection |
| **Pylint** | Python | Code analysis, anti-patterns |
| **ESLint** | JavaScript | Linting, performance rules |
| **Semgrep** | Multi-language | Pattern-based code search |
| **ast-grep** | Multi-language | AST-based pattern matching |

### Profiling Tools

| Tool | Use Case |
|------|----------|
| **Intel VTune** | CPU and power analysis |
| **perf** (Linux) | CPU profiling |
| **py-spy** (Python) | Python profiling |
| **async-profiler** (Java) | JVM profiling |
| **Chrome DevTools** | JavaScript profiling |

### Running Semgrep for Anti-Patterns

```bash
# Install semgrep
pip install semgrep

# Run with performance rules
semgrep --config=p/performance ./src

# Run with specific language rules
semgrep --config=p/java ./src
semgrep --config=p/python ./src
```

---

## Quick Detection Script

Create a bash script to run all patterns:

```bash
#!/bin/bash
# energy-antipattern-scan.sh

echo "=== Scanning for Energy Anti-Patterns ==="

echo -e "\n--- String Concatenation in Loops ---"
grep -rEn '\+= *"' --include="*.java" --include="*.cs" ./src 2>/dev/null | head -20

echo -e "\n--- SELECT * Queries ---"
grep -rEin 'SELECT \*' --include="*.sql" --include="*.java" --include="*.py" ./src 2>/dev/null | head -20

echo -e "\n--- N+1 Query Patterns ---"
grep -rEn '(for|while).*\{' -A15 --include="*.java" ./src 2>/dev/null | grep -E '\.(find|get|fetch|load)\w*\(' | head -20

echo -e "\n--- Unbuffered I/O ---"
grep -rEn 'new File(Input|Output)Stream\(' --include="*.java" ./src 2>/dev/null | grep -v 'Buffered' | head -20

echo -e "\n--- Object Creation in Loops ---"
grep -rEn '(for|while).*\{' -A20 --include="*.java" ./src 2>/dev/null | grep -E 'new [A-Z][a-zA-Z]+\(' | head -20

echo -e "\n--- Python List Append Anti-Pattern ---"
grep -rEn '^\s*\w+ *= *\[\]' -A5 --include="*.py" ./src 2>/dev/null | grep -E '\.append\(' | head -20

echo -e "\n--- Node.js Sync Operations ---"
grep -rEn '(readFileSync|writeFileSync|existsSync)' --include="*.js" --include="*.ts" ./src 2>/dev/null | head -20

echo -e "\n=== Scan Complete ==="
```

---

## Sources

### Academic & Research

1. **MDPI Electronics (2022)** - "Energy Efficiency Analysis of Code Refactoring Techniques"
   - https://www.mdpi.com/2079-9292/11/3/442

2. **arXiv (2025)** - "ECO: An LLM-Driven Efficient Code Optimizer"
   - https://arxiv.org/html/2503.15669v1

3. **Codegex Research** - "Efficient Pattern-based Static Analysis via Regex Rules"
   - https://ieeexplore.ieee.org/document/10123597/

### Industry Best Practices

4. **Python Wiki** - Performance Tips
   - https://wiki.python.org/moin/PythonSpeed/PerformanceTips

5. **Java Anti-Patterns** - ODI.ch
   - https://www.odi.ch/prog/design/newbies.php

6. **DataCamp** - SQL Query Optimization
   - https://www.datacamp.com/blog/sql-query-optimization

7. **PlanetScale** - N+1 Query Problem
   - https://planetscale.com/blog/what-is-n-1-query-problem-and-how-to-solve-it

### Tools Documentation

8. **Semgrep** - Pattern-based Static Analysis
   - https://semgrep.dev/docs/

9. **SpotBugs** - Java Bug Pattern Detection
   - https://spotbugs.github.io/

10. **Green Software Foundation** - Patterns Catalog
    - https://patterns.greensoftware.foundation

---

## Document Information

- **Created**: February 2026
- **Purpose**: Granular code-level energy anti-pattern detection
- **Usage**: Code review, automated scanning, developer education

---

*"Every unnecessary CPU cycle is wasted energy. These grep patterns help you find the low-hanging fruit—the code patterns that waste resources without providing value."*
