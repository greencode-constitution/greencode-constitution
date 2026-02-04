# C# Energy Anti-Patterns: Detection & Fix Guide

> Agent skill: scan a C# codebase for energy-wasting patterns and apply fixes.

---

## How to Use This Skill

1. Run the **Detect** command for each anti-pattern against the project source tree.
2. Review each match — not every hit is a true positive; use context.
3. Apply the **Fix** pattern, adapting to the surrounding code.

---

## 1. String Concatenation in Loops

**Why it wastes energy**: `System.String` is immutable in C#. Using `+` or `+=` inside a loop creates a new string object every iteration — O(n²) allocations and copies.

### Detect

```bash
grep -rEn 'string.*\+=' --include="*.cs" ./src
grep -rEn '\+= *"' --include="*.cs" ./src

# String concat inside for/while bodies
grep -rEn '(for|while|foreach).*\{' -A20 --include="*.cs" ./src | grep -E '\+ *"|\+= *"'
```

### Bad

```csharp
string result = "";
foreach (var item in items)
{
    result += item.ToString() + ", ";
}
```

### Fix

```csharp
var sb = new StringBuilder();
foreach (var item in items)
{
    sb.Append(item).Append(", ");
}
string result = sb.ToString();

// Or use string.Join:
string result = string.Join(", ", items);
```

---

## 2. Recalculating `.Count` / `.Length` in Loop Condition

**Why it wastes energy**: While `.Length` on arrays is essentially free, `.Count` on some `ICollection` implementations may not be. Caching signals intent and avoids potential overhead.

### Detect

```bash
grep -rEn 'for *\(.*;.*\.(Count|Length)\b' --include="*.cs" ./src
grep -rEn 'while *\(.*\.(Count|Length)\b' --include="*.cs" ./src
```

### Bad

```csharp
for (int i = 0; i < list.Count; i++)
{
    Process(list[i]);
}
```

### Fix

```csharp
// Preferred: use foreach
foreach (var item in list)
{
    Process(item);
}

// Or cache the count:
int count = list.Count;
for (int i = 0; i < count; i++)
{
    Process(list[i]);
}
```

---

## 3. LINQ `.Where().Select()` Double Iteration

**Why it wastes energy**: Chaining LINQ operators creates multiple iterators and delegate invocations. For hot paths, a single loop is more efficient.

### Detect

```bash
grep -rEn '\.Where\(.*\.Select\(' --include="*.cs" ./src
grep -rEn '\.Select\(.*\.Where\(' --include="*.cs" ./src
```

### Bad

```csharp
var names = items
    .Where(x => x.IsActive)
    .Select(x => x.Name)
    .ToList();
```

### Fix

```csharp
var names = new List<string>();
foreach (var item in items)
{
    if (item.IsActive)
        names.Add(item.Name);
}

// Note: LINQ is fine for cold paths. Optimize only when profiling shows a bottleneck.
```

---

## 4. Boxing Value Types in Loops

**Why it wastes energy**: Passing a value type (int, struct) where an `object` is expected causes boxing — a heap allocation per call.

### Detect

```bash
# String.Format with value-type arguments inside loops
grep -rEn '(for|while|foreach)' -A15 --include="*.cs" ./src | grep -E 'String\.Format\('

# Console.WriteLine with value-type args in loops
grep -rEn '(for|while|foreach)' -A15 --include="*.cs" ./src | grep -E 'Console\.Write'
```

### Bad

```csharp
for (int i = 0; i < 100000; i++)
{
    Console.WriteLine(String.Format("Value: {0}", i)); // boxes i
}
```

### Fix

```csharp
for (int i = 0; i < 100000; i++)
{
    Console.WriteLine($"Value: {i}"); // interpolation avoids boxing in modern .NET
}
// Or use .ToString() explicitly:
Console.WriteLine("Value: " + i.ToString());
```

---

## 5. Not Disposing Resources (`IDisposable`)

**Why it wastes energy**: Failing to dispose of streams, connections, and handles leaks OS resources and increases GC pressure.

### Detect

```bash
# new Stream/Reader/Writer without using statement
grep -rEn 'new (File|Stream|Buffered|Memory)(Stream|Reader|Writer)\(' --include="*.cs" ./src | grep -v 'using'

# Database connections without using
grep -rEn 'new (Sql|Npgsql|MySql)Connection\(' --include="*.cs" ./src | grep -v 'using'

# HttpClient created in loops (should be singleton or factory)
grep -rEn 'new HttpClient\(' --include="*.cs" ./src
```

### Bad

```csharp
var stream = new FileStream("data.bin", FileMode.Open);
var reader = new StreamReader(stream);
string content = reader.ReadToEnd();
// never disposed
```

### Fix

```csharp
using (var stream = new FileStream("data.bin", FileMode.Open))
using (var reader = new StreamReader(stream))
{
    string content = reader.ReadToEnd();
}

// C# 8+ using declaration:
using var stream = new FileStream("data.bin", FileMode.Open);
using var reader = new StreamReader(stream);
string content = reader.ReadToEnd();
```

---

## 6. Creating Objects Inside Loops

**Why it wastes energy**: Allocating and GC'ing objects every iteration when they could be created once and reused.

### Detect

```bash
grep -rEn '(for|while|foreach).*\{' -A20 --include="*.cs" ./src | grep -E 'new [A-Z][a-zA-Z]+\('

# Specific expensive objects
grep -rEn '(for|while|foreach)' -A15 --include="*.cs" ./src | grep -E 'new (Regex|HttpClient|JsonSerializer|XmlSerializer)\('
```

### Bad

```csharp
foreach (var line in lines)
{
    var regex = new Regex(@"\d+");
    var match = regex.Match(line);
}
```

### Fix

```csharp
var regex = new Regex(@"\d+", RegexOptions.Compiled);
foreach (var line in lines)
{
    var match = regex.Match(line);
}
```

---

## 7. Not Pre-sizing Collections

**Why it wastes energy**: `List<T>` and `Dictionary<TKey,TValue>` resize and re-copy when capacity is exceeded.

### Detect

```bash
grep -rEn 'new (List|Dictionary|HashSet)<.*>\(\)' --include="*.cs" ./src
```

### Bad

```csharp
var list = new List<string>(); // default capacity
for (int i = 0; i < 100000; i++)
{
    list.Add($"item{i}"); // multiple resizes
}
```

### Fix

```csharp
var list = new List<string>(100000);
for (int i = 0; i < 100000; i++)
{
    list.Add($"item{i}");
}
```

---

## 8. `List.Contains()` When `HashSet` Would Be Better

**Why it wastes energy**: `List.Contains()` is O(n). `HashSet.Contains()` is O(1).

### Detect

```bash
grep -rEn 'List<' -A30 --include="*.cs" ./src | grep -E '\.Contains\('
```

### Bad

```csharp
var allowed = new List<string> { "admin", "editor", "viewer" };
foreach (var user in users)
{
    if (allowed.Contains(user.Role)) // O(n)
        Grant(user);
}
```

### Fix

```csharp
var allowed = new HashSet<string> { "admin", "editor", "viewer" };
foreach (var user in users)
{
    if (allowed.Contains(user.Role)) // O(1)
        Grant(user);
}
```

---

## 9. Database Queries Inside Loops (Entity Framework)

**Why it wastes energy**: Each query has round-trip overhead. Use `Include()` or batch fetching.

### Detect

```bash
grep -rEn '(for|while|foreach)' -A15 --include="*.cs" ./src | grep -E '\.(Find|FirstOrDefault|Single|Where)\('
```

### Bad

```csharp
var orders = db.Orders.ToList();
foreach (var order in orders)
{
    var customer = db.Customers.Find(order.CustomerId); // N+1
    Process(order, customer);
}
```

### Fix

```csharp
var orders = db.Orders.Include(o => o.Customer).ToList();
foreach (var order in orders)
{
    Process(order, order.Customer); // no extra queries
}
```

---

## 10. SELECT * in Queries

**Why it wastes energy**: Fetches columns you don't need, wasting bandwidth, memory, and deserialization cost.

### Detect

```bash
grep -rEin 'SELECT \*' --include="*.cs" ./src
grep -rEin '"SELECT \*' --include="*.cs" ./src
```

### Fix

Select only the columns you need, or use a projection:

```csharp
// Bad
var users = db.Users.ToList();

// Good
var users = db.Users.Select(u => new { u.Id, u.Name, u.Email }).ToList();
```
