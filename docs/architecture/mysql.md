# MySQL Energy Antipatterns

Agent skill for detecting and fixing energy-wasting query and configuration antipatterns in MySQL.

---

## 1. N+1 Query Problem

Repeated single-row queries inside application loops instead of batched fetches.

### Detect

```bash
# Enable slow query log + log queries not using indexes
mysql -u root -p -e "SET GLOBAL slow_query_log = 'ON';"
mysql -u root -p -e "SET GLOBAL long_query_time = 1;"
mysql -u root -p -e "SET GLOBAL log_queries_not_using_indexes = 'ON';"

# Analyze slow query log for repeated patterns
mysqldumpslow -s c /var/log/mysql/mysql-slow.log | head -20

# Or use Percona pt-query-digest
pt-query-digest /var/log/mysql/mysql-slow.log --limit=10
```

```sql
-- Check performance_schema for repeated query patterns
SELECT digest_text, count_star AS calls,
       ROUND(avg_timer_wait/1000000000, 2) AS avg_ms,
       ROUND(sum_timer_wait/1000000000, 2) AS total_ms
FROM performance_schema.events_statements_summary_by_digest
ORDER BY count_star DESC LIMIT 20;
```

```bash
# In application code, search for queries inside loops
grep -rn "\.find\|\.get\|\.query\|\.execute" --include="*.py" --include="*.rb" --include="*.java" --include="*.ts" --include="*.js" . \
  | grep -i "for\|while\|each\|map\|forEach"
```

### Fix

- **Use eager loading** in ORMs:
  - Django: `select_related()` / `prefetch_related()`
  - SQLAlchemy: `joinedload()` / `subqueryload()`
  - Rails: `includes()` / `eager_load()`
  - Hibernate: `JOIN FETCH` / `@BatchSize`
  - Sequelize: `include: [{ model: Related }]`
- **Replace with JOINs**:
  ```sql
  -- Instead of: SELECT * FROM orders WHERE user_id = ?  (in a loop)
  SELECT u.*, o.* FROM users u JOIN orders o ON o.user_id = u.id WHERE u.id IN (1,2,3);
  ```
- **Use `WHERE IN`** for batch lookups instead of per-row queries.

---

## 2. Missing Indexes

Full table scans on large tables waste CPU and I/O.

### Detect

```sql
-- Tables with no indexes at all
SELECT table_schema, table_name, table_rows
FROM information_schema.tables t
WHERE table_schema NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')
  AND table_name NOT IN (
    SELECT DISTINCT table_name FROM information_schema.statistics
    WHERE table_schema = t.table_schema
  )
ORDER BY table_rows DESC;

-- Check global scan counters
SHOW GLOBAL STATUS LIKE 'Select_full_join';
SHOW GLOBAL STATUS LIKE 'Select_scan';

-- Use EXPLAIN on suspect queries
EXPLAIN SELECT * FROM orders WHERE customer_id = 42;
```

```bash
# Find queries not using indexes from slow log
mysql -u root -p -e "SHOW VARIABLES LIKE 'log_queries_not_using_indexes';"
```

### Fix

- **Add indexes on WHERE/JOIN/ORDER BY columns**:
  ```sql
  ALTER TABLE orders ADD INDEX idx_customer_id (customer_id);
  ALTER TABLE orders ADD INDEX idx_created (created_at);
  ```
- **Add composite indexes** for multi-column filters:
  ```sql
  ALTER TABLE orders ADD INDEX idx_customer_status (customer_id, status);
  ```
- **Use covering indexes** to avoid table lookups:
  ```sql
  ALTER TABLE orders ADD INDEX idx_cover (customer_id, status, total);
  ```
- **Validate**: `EXPLAIN SELECT ... ;` — look for `type: ALL` (full scan) → should become `type: ref` or `type: range`.

---

## 3. Slow Queries

Queries exceeding thresholds, consuming excessive server resources.

### Detect

```bash
# Top queries by total time
mysqldumpslow -s t /var/log/mysql/mysql-slow.log | head -20

# Detailed analysis
pt-query-digest /var/log/mysql/mysql-slow.log --limit=10
```

```sql
-- Current long-running queries
SHOW FULL PROCESSLIST;

-- From performance_schema
SELECT digest_text, count_star,
       ROUND(avg_timer_wait/1000000000, 2) AS avg_ms
FROM performance_schema.events_statements_summary_by_digest
ORDER BY sum_timer_wait DESC LIMIT 20;
```

### Fix

- **Add missing indexes** (see above).
- **Avoid `SELECT *`** — select only needed columns.
- **Optimize JOINs** — ensure join columns are indexed and of the same type/charset.
- **Use query cache** or application-level caching for repeated reads.
- **Partition large tables** for time-series data:
  ```sql
  ALTER TABLE logs PARTITION BY RANGE (YEAR(created_at)) (
    PARTITION p2024 VALUES LESS THAN (2025),
    PARTITION p2025 VALUES LESS THAN (2026),
    PARTITION pmax VALUES LESS THAN MAXVALUE
  );
  ```

---

## 4. Unused and Duplicate Indexes

Indexes that are never used waste write I/O and storage.

### Detect

```sql
-- Find unused indexes (zero reads)
SELECT object_schema, object_name, index_name,
       count_read, count_write
FROM performance_schema.table_io_waits_summary_by_index_usage
WHERE index_name IS NOT NULL AND count_read = 0 AND object_schema NOT IN ('mysql', 'sys')
ORDER BY count_write DESC;

-- Find duplicate indexes
SELECT table_schema, table_name,
       GROUP_CONCAT(index_name) AS duplicate_indexes,
       GROUP_CONCAT(column_name ORDER BY seq_in_index) AS columns
FROM information_schema.statistics
WHERE table_schema NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')
GROUP BY table_schema, table_name, column_name
HAVING COUNT(*) > 1;
```

```bash
# Or use Percona pt-duplicate-key-checker
pt-duplicate-key-checker --host=localhost --user=root
```

### Fix

- **Drop unused indexes**: `ALTER TABLE orders DROP INDEX idx_unused;`
- **Drop duplicates** — keep the more selective or covering index.
- **Monitor** — each index adds write overhead. Dropping unused indexes can improve write throughput significantly.

---

## 5. Untuned Buffer Pool

Default InnoDB buffer pool size is too small, causing excessive disk I/O.

### Detect

```sql
-- Check current buffer pool size
SHOW VARIABLES LIKE 'innodb_buffer_pool_size';

-- Check buffer pool hit ratio (should be >99%)
SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool_read_requests';
SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool_reads';
-- Hit ratio = 1 - (reads / read_requests)

-- Check if buffer pool is too small
SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool_pages_free';
```

### Fix

- **Set `innodb_buffer_pool_size`** to ~70-80% of available RAM on dedicated DB servers:
  ```ini
  [mysqld]
  innodb_buffer_pool_size = 12G  # for a 16GB server
  innodb_buffer_pool_instances = 8
  ```
- **Enable buffer pool dump/load** for faster restarts:
  ```ini
  innodb_buffer_pool_dump_at_shutdown = ON
  innodb_buffer_pool_load_at_startup = ON
  ```

---

## 6. Too Many Connections

High `max_connections` wastes memory (~10MB per idle connection).

### Detect

```sql
-- Check max vs actual connections
SHOW VARIABLES LIKE 'max_connections';
SHOW GLOBAL STATUS LIKE 'Threads_connected';
SHOW GLOBAL STATUS LIKE 'Max_used_connections';
```

### Fix

- **Lower `max_connections`** to actual peak + headroom.
- **Use connection pooling** (ProxySQL, MySQL Router, application-level pooling).
- **Use persistent connections** in the application to avoid connection overhead.
