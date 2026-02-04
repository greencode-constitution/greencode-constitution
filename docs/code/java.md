# Java Energy Anti-Patterns: Detection & Fix Guide

> Agent skill: scan a Java codebase for energy-wasting patterns and apply fixes.

---

## How to Use This Skill

1. Run the **Detect** command for each anti-pattern against the project source tree.
2. Review each match — not every hit is a true positive; use context.
3. Apply the **Fix** pattern, adapting to the surrounding code.

---

## 1. String Concatenation in Loops

**Why it wastes energy**: `String` is immutable in Java. Using `+` or `+=` inside a loop creates a new `String` object every iteration, turning O(n) work into O(n²) allocations and copies.

### Detect

```bash
# Find += with a string literal (common in loops)
grep -rEn '\+= *"' --include="*.java" ./src

# Find empty-string initializations that precede loop concatenation
grep -rEn 'String.*= *"";' --include="*.java" ./src

# Find string + operator inside for/while bodies (20-line window)
grep -rEn '(for|while).*\{' -A20 --include="*.java" ./src | grep -E '\+ *"|\+= *"'
```

### Bad

```java
String result = "";
for (int i = 0; i < 10000; i++) {
    result += "item" + i + ", ";
}
```

### Fix

```java
StringBuilder sb = new StringBuilder();
for (int i = 0; i < 10000; i++) {
    sb.append("item").append(i).append(", ");
}
String result = sb.toString();
```

---

## 2. Repeated String Method Calls in Loops

**Why it wastes energy**: Calling `.toUpperCase()`, `.toLowerCase()`, `.trim()` on a value that doesn't change between iterations repeats work pointlessly.

### Detect

```bash
grep -rEn '(for|while).*\{' -A30 --include="*.java" ./src | grep -E '\.(toUpperCase|toLowerCase|trim|substring)\(\)'
```

### Bad

```java
for (Item item : items) {
    if (item.getName().toUpperCase().equals(searchTerm.toUpperCase())) {
        // searchTerm.toUpperCase() recalculated every iteration
    }
}
```

### Fix

```java
String searchTermUpper = searchTerm.toUpperCase();
for (Item item : items) {
    if (item.getName().toUpperCase().equals(searchTermUpper)) {
        // Computed once
    }
}
```

---

## 3. Recalculating `.size()` / `.length()` in Loop Condition

**Why it wastes energy**: The method is invoked on every iteration even when the collection is not modified inside the loop.

### Detect

```bash
grep -rEn 'for *\(.*;.*\.(size|length)\(\)' --include="*.java" ./src
grep -rEn 'while *\(.*\.(size|length)\(\)' --include="*.java" ./src
```

### Bad

```java
for (int i = 0; i < list.size(); i++) {
    process(list.get(i));
}
```

### Fix

```java
int size = list.size();
for (int i = 0; i < size; i++) {
    process(list.get(i));
}
// Or use enhanced for-loop:
for (Item item : list) {
    process(item);
}
```

---

## 4. Invariant Computation Inside Loops

**Why it wastes energy**: Expressions whose result never changes across iterations waste CPU cycles being re-evaluated.

### Detect

```bash
# Math operations inside loops
grep -rEn 'for.*\{' -A20 --include="*.java" ./src | grep -E 'Math\.(sqrt|pow|sin|cos|log|exp)\('

# Regex compilation inside loops
grep -rEn '(for|while)' -A10 --include="*.java" ./src | grep -E 'Pattern\.compile\('
```

### Bad

```java
for (int i = 0; i < n; i++) {
    double factor = Math.sqrt(baseValue) * Math.PI;
    result[i] = data[i] * factor;
}
```

### Fix

```java
double factor = Math.sqrt(baseValue) * Math.PI;
for (int i = 0; i < n; i++) {
    result[i] = data[i] * factor;
}
```

---

## 5. Nested Loops Where a HashSet/HashMap Would Suffice

**Why it wastes energy**: A `.contains()` call on an `ArrayList` is O(n). Inside another loop that becomes O(n×m). A `HashSet` gives O(1) lookups.

### Detect

```bash
grep -rEn 'for.*\{' -A15 --include="*.java" ./src | grep -E '\.contains\('
```

### Bad

```java
List<String> allowed = getWhitelist();
for (String item : incoming) {
    if (allowed.contains(item)) { // O(n) per call
        accept(item);
    }
}
```

### Fix

```java
Set<String> allowed = new HashSet<>(getWhitelist());
for (String item : incoming) {
    if (allowed.contains(item)) { // O(1) per call
        accept(item);
    }
}
```

---

## 6. Creating Objects Inside Loops

**Why it wastes energy**: Allocating and later garbage-collecting objects that could be created once and reused.

### Detect

```bash
# General: new Object() inside loops
grep -rEn '(for|while).*\{' -A20 --include="*.java" ./src | grep -E 'new [A-Z][a-zA-Z]+\('

# Specific expensive objects inside loops
grep -rEn '(for|while)' -A15 --include="*.java" ./src | grep -E 'new (SimpleDateFormat|DecimalFormat|Pattern|ObjectMapper|Gson)\('
```

### Bad

```java
for (int i = 0; i < 1000; i++) {
    SimpleDateFormat sdf = new SimpleDateFormat("yyyy-MM-dd");
    String date = sdf.format(dates[i]);
}
```

### Fix

```java
SimpleDateFormat sdf = new SimpleDateFormat("yyyy-MM-dd");
for (int i = 0; i < 1000; i++) {
    String date = sdf.format(dates[i]);
}
```

---

## 7. Autoboxing in Loops

**Why it wastes energy**: `Long sum = 0L; sum += i;` silently creates a new `Long` object on every iteration.

### Detect

```bash
# Wrapper types used as accumulators
grep -rEn '(Integer|Long|Double|Float|Boolean) \w+ *= *[0-9]' --include="*.java" ./src

# Wrapper types combined with += operations
grep -rEn '(Integer|Long|Double|Float) \w+' -A10 --include="*.java" ./src | grep -E '\+= *'

# Wrapper types as loop variables
grep -rEn 'for *\( *(Integer|Long|Double|Float)' --include="*.java" ./src
```

### Bad

```java
Long sum = 0L;
for (int i = 0; i < 1000000; i++) {
    sum += i;  // autoboxing every iteration
}
```

### Fix

```java
long sum = 0L;
for (int i = 0; i < 1000000; i++) {
    sum += i;  // primitive, no object creation
}
```

---

## 8. Missing Resource Closure (try-with-resources)

**Why it wastes energy**: Leaked file handles, streams, and connections hold OS resources indefinitely and can exhaust pools.

### Detect

```bash
# Stream/Reader/Writer created without try-with-resources
grep -rEn 'new (File|Buffered|Input|Output)(Stream|Reader|Writer)\(' --include="*.java" ./src | grep -v 'try *('

# JDBC connections without try-with-resources
grep -rEn '(getConnection|createStatement|prepareStatement)\(' --include="*.java" ./src
```

### Bad

```java
FileInputStream fis = new FileInputStream("file.txt");
// use fis...
// if an exception is thrown, fis is never closed
```

### Fix

```java
try (FileInputStream fis = new FileInputStream("file.txt")) {
    // use fis...
}  // automatically closed
```

---

## 9. Unbuffered I/O

**Why it wastes energy**: A raw `FileInputStream.read()` makes one system call per byte. Buffering reduces this by ~1000x.

### Detect

```bash
# FileInputStream/FileOutputStream without Buffered wrapper
grep -rEn 'new File(Input|Output)Stream\(' --include="*.java" ./src | grep -v 'Buffered'

# FileReader/FileWriter without Buffered wrapper
grep -rEn 'new File(Reader|Writer)\(' --include="*.java" ./src | grep -v 'Buffered'
```

### Bad

```java
FileInputStream fis = new FileInputStream("file.txt");
int b;
while ((b = fis.read()) != -1) {
    process(b);
}
```

### Fix

```java
try (BufferedInputStream bis = new BufferedInputStream(new FileInputStream("file.txt"))) {
    int b;
    while ((b = bis.read()) != -1) {
        process(b);
    }
}
```

---

## 10. Database Queries Inside Loops

**Why it wastes energy**: Each query has round-trip overhead. Batch fetching amortizes this cost.

### Detect

```bash
grep -rEn '(for|while).*\{' -A15 --include="*.java" ./src | grep -E '\.(find|get|fetch|load|query|select|execute)\w*\('
```

### Bad

```java
for (Long id : userIds) {
    User user = userRepository.findById(id);
    process(user);
}
```

### Fix

```java
List<User> users = userRepository.findAllById(userIds);
for (User user : users) {
    process(user);
}
```

---

## 11. Logging Without Guard in Loops

**Why it wastes energy**: Each varargs logging call allocates an `Object[]` array, even if the log level is disabled.

### Detect

```bash
# Logging inside loops without level guard
grep -rEn '(for|while).*\{' -A20 --include="*.java" ./src | grep -E '(logger|LOG|log)\.(debug|trace|info)\('

# debug() calls with no isDebugEnabled check
grep -rEn 'log.*\.debug\(' --include="*.java" ./src | grep -v 'isDebugEnabled'
```

### Bad

```java
for (int i = 0; i < 10000; i++) {
    logger.debug("Processing item: {}", i);
}
```

### Fix

```java
if (logger.isDebugEnabled()) {
    for (int i = 0; i < 10000; i++) {
        logger.debug("Processing item: {}", i);
    }
}
```

---

## 12. Not Pre-sizing Collections

**Why it wastes energy**: Default-sized collections resize and re-hash/copy multiple times as they grow.

### Detect

```bash
# ArrayList/HashMap/HashSet created without initial capacity
grep -rEn 'new (ArrayList|HashMap|HashSet|StringBuilder)\(\)' --include="*.java" ./src
```

### Bad

```java
List<String> list = new ArrayList<>();  // default capacity 10
for (int i = 0; i < 100000; i++) {
    list.add("item" + i);  // multiple resizes
}
```

### Fix

```java
List<String> list = new ArrayList<>(100000);
for (int i = 0; i < 100000; i++) {
    list.add("item" + i);
}
```

---

## 13. Wrong Collection Type for the Access Pattern

**Why it wastes energy**: `LinkedList.get(i)` is O(n). `ArrayList` with frequent `add(0, x)` is O(n) per insert. Using `List.contains()` when a `Set` would give O(1).

### Detect

```bash
# LinkedList with index-based access
grep -rEn 'LinkedList' -A20 --include="*.java" ./src | grep -E '\.get\([0-9i]'

# ArrayList with frequent insert-at-head
grep -rEn 'ArrayList' -A20 --include="*.java" ./src | grep -E '\.add\(0,'

# List.contains() when Set would be better
grep -rEn '(ArrayList|LinkedList)' -A30 --include="*.java" ./src | grep -E '\.contains\('
```

### Fix

Choose the correct collection:

| Operation | Best type |
|---|---|
| Random access by index | `ArrayList` |
| Frequent insert/remove at head | `LinkedList` or `ArrayDeque` |
| Membership checks | `HashSet` |
| Sorted iteration | `TreeSet` |

---

## 14. String.format() in Tight Loops

**Why it wastes energy**: `String.format` parses the format string every call. StringBuilder or direct concatenation is faster in hot loops.

### Detect

```bash
grep -rEn '(for|while)' -A15 --include="*.java" ./src | grep 'String\.format\('
```

### Bad

```java
for (Record r : records) {
    String line = String.format("Name: %s, Age: %d", r.getName(), r.getAge());
    output.add(line);
}
```

### Fix

```java
StringBuilder sb = new StringBuilder();
for (Record r : records) {
    sb.setLength(0);
    sb.append("Name: ").append(r.getName()).append(", Age: ").append(r.getAge());
    output.add(sb.toString());
}
```

---

## 15. Reflection in Loops

**Why it wastes energy**: `getMethod()`, `getField()`, `invoke()` bypass JIT optimizations and involve security checks on every call.

### Detect

```bash
grep -rEn '(for|while)' -A15 --include="*.java" ./src | grep -E '\.(getMethod|getField|invoke)\('
```

### Fix

Cache the `Method`/`Field` object outside the loop and call `setAccessible(true)` once.

---

## 16. Creating Threads in Loops

**Why it wastes energy**: Thread creation has significant OS overhead. Use a thread pool instead.

### Detect

```bash
grep -rEn '(for|while)' -A15 --include="*.java" ./src | grep 'new Thread\('
```

### Bad

```java
for (Task task : tasks) {
    new Thread(() -> task.execute()).start();
}
```

### Fix

```java
ExecutorService pool = Executors.newFixedThreadPool(Runtime.getRuntime().availableProcessors());
for (Task task : tasks) {
    pool.submit(() -> task.execute());
}
pool.shutdown();
```

---

## 17. Static Collections Holding References Too Long

**Why it wastes energy**: Static collections live for the entire JVM lifetime, preventing garbage collection of their contents, which keeps memory pressure high and GC cycles expensive.

### Detect

```bash
grep -rEn 'static.*(List|Map|Set|Collection).*=' --include="*.java" ./src
```

### Fix

Consider using weak references (`WeakHashMap`), explicit cleanup methods, or scoping the collection to the method/request lifecycle.

---

## 18. SELECT * in Queries

**Why it wastes energy**: Fetches columns you don't need, wasting bandwidth, memory, and deserialization cost.

### Detect

```bash
grep -rEin '"SELECT \*' --include="*.java" ./src
grep -rEn '\.findAll\(|\.getAll\(' --include="*.java" ./src
```

### Fix

Select only the columns you need, or use a DTO projection in your ORM.

---

## 19. Missing HTTP Response Compression

**Why it wastes energy**: Serving uncompressed HTTP responses wastes bandwidth and energy. Most Java web frameworks support gzip/brotli but it's often not enabled by default.

### Detect

```bash
# Spring Boot: check if compression is enabled in properties
grep -rEn 'server\.compression' --include="*.properties" --include="*.yml" --include="*.yaml" .
grep -rL 'server\.compression\.enabled' --include="*.properties" --include="*.yml" . | xargs grep -l 'server\.port'

# Servlet filter: check for GzipFilter or CompressingFilter
grep -rEn 'GzipFilter\|CompressingFilter\|GzipServletFilter' --include="*.java" --include="*.xml" ./src

# Check if spring-boot-starter-web is present but compression unconfigured
grep -q 'spring-boot-starter-web' pom.xml build.gradle 2>/dev/null && \
  grep -rqL 'compression.enabled' --include="*.properties" --include="*.yml" . && \
  echo "Spring Web present but compression not configured"
```

### Bad

```yaml
# application.yml — no compression config
server:
  port: 8080
```

### Fix

```yaml
# application.yml
server:
  port: 8080
  compression:
    enabled: true
    mime-types: application/json,application/xml,text/html,text/css,application/javascript
    min-response-size: 1024
```

---

## 20. Synchronous Blocking HTTP Calls

**Why it wastes energy**: Blocking HTTP calls (`HttpURLConnection`, synchronous `RestTemplate`) hold threads idle while waiting for responses. Async/non-blocking clients let threads handle other work during I/O waits.

### Detect

```bash
# HttpURLConnection (always blocking)
grep -rEn 'HttpURLConnection\|openConnection\(\)' --include="*.java" ./src

# RestTemplate (synchronous, deprecated for new code)
grep -rEn 'RestTemplate\|restTemplate\.' --include="*.java" ./src

# Synchronous OkHttp calls
grep -rEn '\.execute\(\)' --include="*.java" ./src | grep -i 'http\|okhttp\|call'

# Missing WebClient or async HTTP usage
grep -rL 'WebClient\|HttpClient\.newHttpClient\|CompletableFuture' --include="*.java" ./src \
  | xargs grep -l 'RestTemplate\|HttpURLConnection'
```

### Bad

```java
// Blocks the thread until response arrives
RestTemplate restTemplate = new RestTemplate();
String result = restTemplate.getForObject("http://service/api/data", String.class);
```

### Fix

```java
// Spring WebClient (non-blocking)
WebClient client = WebClient.create("http://service");
Mono<String> result = client.get()
    .uri("/api/data")
    .retrieve()
    .bodyToMono(String.class);

// Java 11+ HttpClient (async)
HttpClient client = HttpClient.newHttpClient();
CompletableFuture<HttpResponse<String>> future = client.sendAsync(
    HttpRequest.newBuilder(URI.create("http://service/api/data")).build(),
    HttpResponse.BodyHandlers.ofString()
);
```
