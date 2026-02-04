# PostgreSQL Energy Antipatterns

Agent skill for detecting and fixing energy-wasting query and configuration antipatterns in PostgreSQL.

---

## 1. N+1 Query Problem

An initial query followed by N additional queries per row, causing massive CPU/IO waste.

### Detect

```sql
-- Enable pg_stat_statements
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Find most frequently called queries (N+1 pattern = same query called thousands of times)
SELECT calls, mean_exec_time::numeric(10,2) AS avg_ms,
       total_exec_time::numeric(10,2) AS total_ms, left(query, 120) AS query
FROM pg_stat_statements
ORDER BY calls DESC LIMIT 20;

-- Group similar queries to spot N+1 patterns
SELECT left(query, 100) AS pattern, count(*) AS variants, sum(calls) AS total_calls
FROM pg_stat_statements
GROUP BY left(query, 100) HAVING count(*) > 1
ORDER BY sum(calls) DESC LIMIT 20;
```

```bash
# In application code, search for ORM queries inside loops
grep -rn "\.find\|\.get\|\.load\|\.query" --include="*.py" --include="*.rb" --include="*.java" --include="*.ts" --include="*.js" . \
  | grep -i "for\|while\|each\|map\|forEach"
```

### Fix

- **Use eager loading** in ORMs:
  - Django: `select_related()` / `prefetch_related()`
  - SQLAlchemy: `joinedload()` / `subqueryload()`
  - Rails: `includes()` / `eager_load()`
  - Hibernate: `@Fetch(FetchMode.JOIN)` or `JOIN FETCH` in HQL
  - Entity Framework: `.Include()`
- **Replace loops with JOINs**:
  ```sql
  -- Instead of N+1: SELECT * FROM orders WHERE user_id = ?  (per user)
  -- Use a single JOIN:
  SELECT u.*, o.* FROM users u JOIN orders o ON o.user_id = u.id;
  ```
- **Use DataLoader pattern** for GraphQL resolvers to batch requests.

---

## 2. Missing Indexes (Sequential Scans on Large Tables)

Full table scans on large tables waste CPU, memory, and disk I/O.

### Detect

```sql
-- Tables with high sequential scan counts relative to index scans
SELECT schemaname, relname AS table_name,
       seq_scan, seq_tup_read, idx_scan, n_live_tup AS row_count
FROM pg_stat_user_tables
WHERE seq_scan > 0 AND n_live_tup > 10000
ORDER BY seq_tup_read DESC LIMIT 20;

-- Tables where seq scans outnumber index scans (missing indexes)
SELECT schemaname || '.' || relname AS table,
       seq_scan - idx_scan AS excess_seq_scans,
       pg_size_pretty(pg_relation_size(relid)) AS size
FROM pg_stat_user_tables
WHERE seq_scan - idx_scan > 0
ORDER BY seq_scan - idx_scan DESC LIMIT 20;

-- Find slow queries doing seq scans
SELECT query, calls, mean_exec_time::numeric(10,2) AS avg_ms
FROM pg_stat_statements
WHERE query ILIKE '%WHERE%' AND mean_exec_time > 100
ORDER BY total_exec_time DESC LIMIT 20;
```

### Fix

- **Add B-Tree indexes** on columns used in WHERE, JOIN, ORDER BY:
  ```sql
  CREATE INDEX idx_orders_user_id ON orders(user_id);
  CREATE INDEX idx_orders_created ON orders(created_at);
  ```
- **Use composite indexes** for multi-column queries:
  ```sql
  CREATE INDEX idx_orders_user_status ON orders(user_id, status);
  ```
- **Use partial indexes** for frequently filtered subsets:
  ```sql
  CREATE INDEX idx_active_orders ON orders(created_at) WHERE status = 'active';
  ```
- **Use GIN indexes** for JSONB/array columns:
  ```sql
  CREATE INDEX idx_metadata ON products USING GIN(metadata);
  ```
- **Use BRIN indexes** for naturally ordered columns (timestamps):
  ```sql
  CREATE INDEX idx_logs_ts ON logs USING BRIN(created_at);
  ```
- **Validate with EXPLAIN ANALYZE** before and after:
  ```sql
  EXPLAIN ANALYZE SELECT * FROM orders WHERE user_id = 42;
  ```

---

## 3. Slow Queries

Queries exceeding acceptable thresholds, consuming excessive CPU time.

### Detect

```bash
# Enable slow query logging
psql -U postgres -c "ALTER SYSTEM SET log_min_duration_statement = 1000;"
psql -U postgres -c "SELECT pg_reload_conf();"
```

```sql
-- Top queries by total execution time
SELECT calls, mean_exec_time::numeric(10,2) AS avg_ms,
       total_exec_time::numeric(10,2) AS total_ms, left(query, 120) AS query
FROM pg_stat_statements
ORDER BY total_exec_time DESC LIMIT 20;

-- Reset stats to measure fresh
SELECT pg_stat_statements_reset();
```

### Fix

- **Add missing indexes** (see above).
- **Rewrite queries** — avoid `SELECT *`, use specific columns.
- **Use materialized views** for expensive aggregations:
  ```sql
  CREATE MATERIALIZED VIEW monthly_sales AS
    SELECT date_trunc('month', created_at) AS month, sum(amount) AS total
    FROM orders GROUP BY 1;
  -- Refresh periodically
  REFRESH MATERIALIZED VIEW CONCURRENTLY monthly_sales;
  ```
- **Increase `work_mem`** for sort/hash-heavy queries (tune per-session, not globally).
- **Use connection pooling** (PgBouncer) to reduce connection overhead.

---

## 4. Index Bloat

Indexes grow oversized due to PostgreSQL MVCC, degrading read and write performance.

### Detect

```sql
-- Check index sizes vs table sizes
SELECT schemaname || '.' || tablename AS table,
       pg_size_pretty(pg_table_size(schemaname || '.' || tablename)) AS table_size,
       pg_size_pretty(pg_indexes_size(schemaname || '.' || tablename)) AS index_size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_indexes_size(schemaname || '.' || tablename) DESC LIMIT 20;

-- Find unused indexes (zero scans)
SELECT schemaname || '.' || relname AS table,
       indexrelname AS index, idx_scan,
       pg_size_pretty(pg_relation_size(indexrelid)) AS size
FROM pg_stat_user_indexes
WHERE idx_scan = 0 AND schemaname = 'public'
ORDER BY pg_relation_size(indexrelid) DESC;
```

### Fix

- **Drop unused indexes**: `DROP INDEX idx_name;`
- **Reindex bloated indexes**: `REINDEX INDEX idx_name;`
- **Run VACUUM** regularly (autovacuum should be enabled and tuned).
- **Monitor** — each index adds ~5-15% overhead to writes. Dropping unused indexes can improve write throughput by ~30%.

---

## 5. Untuned Configuration

Default PostgreSQL config wastes resources or underperforms on available hardware.

### Detect

```sql
-- Check key settings
SHOW shared_buffers;        -- Should be ~25% of RAM
SHOW effective_cache_size;  -- Should be ~75% of RAM
SHOW work_mem;              -- Default 4MB is often too low
SHOW maintenance_work_mem;
SHOW max_connections;       -- High values waste memory (~10MB per idle connection)
```

### Fix

- **Tune shared_buffers** to ~25% of system RAM.
- **Tune effective_cache_size** to ~75% of system RAM.
- **Lower max_connections** and use PgBouncer for connection pooling.
- **Use `pgtune`** for automated config recommendations based on hardware:
  ```bash
  # https://pgtune.leopard.in.ua/
  # Input: DB version, OS type, RAM, CPU count, storage type, workload type
  ```
