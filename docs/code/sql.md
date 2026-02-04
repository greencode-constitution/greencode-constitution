# SQL Energy Anti-Patterns: Detection & Fix Guide

> Agent skill: scan a codebase for energy-wasting SQL patterns and apply fixes. These patterns apply regardless of the host language.

---

## How to Use This Skill

1. Run the **Detect** command for each anti-pattern against the project source tree.
2. Detection commands search across common file types (`.sql`, `.java`, `.py`, `.js`, `.ts`, `.rb`, `.cs`, `.php`, `.go`). Adjust the `--include` flags as needed.
3. Review each match — not every hit is a true positive; use context.
4. Apply the **Fix** pattern, adapting to the surrounding code.

---

## 1. SELECT * Queries

**Why it wastes energy**: Fetches all columns when only a subset is needed. This wastes network bandwidth, memory for result set allocation, and CPU for deserializing unused columns.

### Detect

```bash
# In SQL files
grep -rEin 'SELECT \*' --include="*.sql" ./src

# In application code (string literals)
grep -rEin 'SELECT \*' --include="*.java" --include="*.py" --include="*.js" --include="*.ts" --include="*.rb" --include="*.cs" --include="*.go" --include="*.php" ./src

# ORM methods that implicitly select all columns
grep -rEn '\.findAll\(|\.getAll\(|\.fetchAll\(' --include="*.java" --include="*.js" --include="*.ts" ./src
```

### Bad

```sql
SELECT * FROM users WHERE status = 'active';
```

### Fix

```sql
SELECT id, name, email FROM users WHERE status = 'active';
```

For ORMs, use projections / `.select()` / `.only()` / DTO projections.

---

## 2. N+1 Query Problem

**Why it wastes energy**: One query fetches N parent rows, then N separate queries fetch related child rows. Each query incurs connection, parsing, and network overhead.

### Detect

```bash
# Django (Python)
grep -rEn '\.objects\.(all|filter)\(' -A10 --include="*.py" ./src | grep -E 'for .* in'
grep -rEn '\.objects\.(all|filter|get)\(' --include="*.py" ./src | grep -v -E '(select_related|prefetch_related)'

# SQLAlchemy (Python)
grep -rEn 'session\.query\(' -A10 --include="*.py" ./src | grep -E 'for .* in'

# Rails (Ruby)
grep -rEn '\.(all|where|find)\b' -A5 --include="*.rb" ./src | grep -E '\.each'

# JPA / Hibernate (Java)
grep -rEn 'for.*:.*\{' -A10 --include="*.java" ./src | grep -E '\.(get|find)[A-Z]\w*\(\)'

# Node.js / Mongoose
grep -rEn '(for|while|forEach)' -A10 --include="*.js" --include="*.ts" ./src | grep -E '(\.find\(|\.findOne\(|await.*Model\.)'
```

### Fix by ORM

| ORM | Fix |
|---|---|
| Django | `.select_related('relation')` (FK/OneToOne) or `.prefetch_related('relation')` (M2M) |
| SQLAlchemy | `joinedload(Model.relation)` or `subqueryload(Model.relation)` |
| Rails | `.includes(:relation)` or `.eager_load(:relation)` |
| JPA | `@EntityGraph` or `JOIN FETCH` in JPQL |
| Mongoose | `.populate('relation')` |
| Entity Framework | `.Include(e => e.Relation)` |

---

## 3. Queries Inside Loops

**Why it wastes energy**: Each query has TCP round-trip, parse, plan, and execute overhead. Batching into a single query with `IN (...)` or a join eliminates N-1 round-trips.

### Detect

```bash
# Java
grep -rEn '(for|while).*\{' -A15 --include="*.java" ./src | grep -E '\.(find|get|fetch|load|query|select|execute)\w*\('

# Python
grep -rEn 'for .* in .*:' -A10 --include="*.py" ./src | grep -E '(cursor\.|\.execute\(|\.query\(|session\.)'

# JavaScript / Node.js
grep -rEn '(for|while|forEach)' -A10 --include="*.js" --include="*.ts" ./src | grep -E '(\.find\(|\.findOne\(|\.query\(|await.*Model\.)'

# Ruby
grep -rEn '(\.each|\.times|\.map)' -A10 --include="*.rb" ./src | grep -E '\.(find|find_by|where)\('

# C#
grep -rEn '(for|while|foreach)' -A15 --include="*.cs" ./src | grep -E '\.(Find|FirstOrDefault|Single|Where)\('
```

### Bad

```python
for user_id in user_ids:
    user = cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
```

### Fix

```python
placeholders = ",".join(["%s"] * len(user_ids))
cursor.execute(f"SELECT id, name FROM users WHERE id IN ({placeholders})", user_ids)
```

---

## 4. Missing Indexes on Filtered / Joined / Sorted Columns

**Why it wastes energy**: Without indexes, the database performs full table scans — reading every row from disk even when only a few match.

### Detect

```bash
# Find columns used in WHERE clauses
grep -rEin 'WHERE\s+\w+\s*=' --include="*.sql" ./src

# Find columns used in JOINs
grep -rEin 'JOIN.*ON\s+\w+\.\w+\s*=' --include="*.sql" ./src

# Find columns used in ORDER BY
grep -rEin 'ORDER BY \w+' --include="*.sql" ./src

# Check existing indexes
grep -rEin 'CREATE INDEX|CREATE UNIQUE INDEX' --include="*.sql" ./src
```

### Fix

```sql
-- Add index on frequently filtered column
CREATE INDEX idx_users_status ON users (status);

-- Add composite index for common query pattern
CREATE INDEX idx_orders_customer_date ON orders (customer_id, created_at);
```

Cross-reference the WHERE/JOIN/ORDER BY columns against existing indexes to find gaps.

---

## 5. Unbounded Queries (Missing LIMIT)

**Why it wastes energy**: Queries without `LIMIT` fetch the entire table, even when the application only displays the first page.

### Detect

```bash
# SELECT without LIMIT
grep -rEin 'SELECT .* FROM' --include="*.sql" --include="*.py" --include="*.java" --include="*.js" --include="*.rb" ./src | grep -v -i 'LIMIT'

# ORM .all() calls without pagination
grep -rEn '\.all\(\)' --include="*.py" --include="*.rb" --include="*.java" ./src
```

### Bad

```sql
SELECT id, name FROM products WHERE category = 'electronics';
-- returns 500,000 rows when UI shows 20
```

### Fix

```sql
SELECT id, name FROM products WHERE category = 'electronics'
ORDER BY name LIMIT 20 OFFSET 0;
```

---

## 6. Using `LIKE '%term%'` (Leading Wildcard)

**Why it wastes energy**: A leading `%` prevents index usage, forcing a full table scan.

### Detect

```bash
grep -rEin "LIKE\s*['\"]%\w" --include="*.sql" --include="*.py" --include="*.java" --include="*.js" --include="*.rb" --include="*.cs" ./src
```

### Bad

```sql
SELECT * FROM products WHERE name LIKE '%widget%';
```

### Fix

- Use full-text search (`MATCH AGAINST`, `to_tsvector`/`to_tsquery`, Elasticsearch).
- If prefix search is sufficient, use `LIKE 'widget%'` which can use an index.
- Add a full-text index and use the database's native search:

```sql
-- PostgreSQL
SELECT id, name FROM products WHERE to_tsvector('english', name) @@ to_tsquery('widget');
```

---

## 7. Correlated Subqueries

**Why it wastes energy**: A correlated subquery executes once per row of the outer query — potentially O(n²).

### Detect

```bash
# Subquery referencing outer table
grep -rEin 'SELECT.*\(SELECT' --include="*.sql" --include="*.py" --include="*.java" --include="*.js" ./src
```

### Bad

```sql
SELECT name,
       (SELECT COUNT(*) FROM orders o WHERE o.user_id = u.id) as order_count
FROM users u;
```

### Fix

```sql
SELECT u.name, COUNT(o.id) as order_count
FROM users u
LEFT JOIN orders o ON o.user_id = u.id
GROUP BY u.name;
```

---

## 8. INSERT in a Loop Instead of Bulk INSERT

**Why it wastes energy**: Each INSERT is a separate transaction with fsync overhead. Bulk insert batches them.

### Detect

```bash
# INSERT inside loops
grep -rEn '(for|while)' -A10 --include="*.py" --include="*.java" --include="*.js" --include="*.rb" ./src | grep -Ei 'INSERT INTO'

# ORM .save() / .create() inside loops
grep -rEn '(for|while|\.each|forEach)' -A10 --include="*.py" --include="*.rb" --include="*.js" ./src | grep -E '\.(save|create)\('
```

### Bad

```python
for item in items:
    cursor.execute("INSERT INTO products (name, price) VALUES (%s, %s)", (item.name, item.price))
```

### Fix

```python
# Use executemany
cursor.executemany(
    "INSERT INTO products (name, price) VALUES (%s, %s)",
    [(item.name, item.price) for item in items]
)

# Or bulk INSERT syntax:
# INSERT INTO products (name, price) VALUES (...), (...), (...)

# Django
Product.objects.bulk_create([Product(name=i.name, price=i.price) for i in items])
```
