# Redis Energy Antipatterns

Agent skill for detecting and fixing energy-wasting antipatterns in Redis deployments.

---

## 1. Low Cache Hit Ratio

A hit ratio below 90% means most lookups miss the cache and hit the database anyway, wasting both Redis and database resources.

### Detect

```bash
# Get hit/miss stats
redis-cli INFO stats | grep -E "keyspace_hits|keyspace_misses"

# Calculate hit ratio
redis-cli INFO stats | awk -F: '
  /keyspace_hits/ {hits=$2}
  /keyspace_misses/ {misses=$2}
  END {
    total = hits + misses
    if (total > 0) printf "Hit ratio: %.2f%% (%d hits, %d misses)\n", hits/total*100, hits, misses
  }'
```

### Fix

- **Cache the right data** — focus on frequently read, rarely written data.
- **Pre-warm the cache** on deployment with commonly accessed keys.
- **Use appropriate TTLs** — too short causes misses, too long causes stale data.
- **Use cache-aside pattern** in application code:
  ```python
  def get_user(user_id):
      cached = redis.get(f"user:{user_id}")
      if cached:
          return json.loads(cached)
      user = db.query("SELECT * FROM users WHERE id = %s", user_id)
      redis.setex(f"user:{user_id}", 3600, json.dumps(user))
      return user
  ```
- **Monitor per-key patterns** to identify frequently missed keys and add them to cache logic.

---

## 2. Large Keys (Memory Waste)

Individual keys storing very large values consume excessive memory and slow down operations.

### Detect

```bash
# Find large keys (scans entire keyspace)
redis-cli --bigkeys

# Memory usage of a specific key
redis-cli MEMORY USAGE key_name

# Check overall memory
redis-cli INFO memory | grep -E "used_memory_human|maxmemory_human|mem_fragmentation_ratio"
```

### Fix

- **Break large values** into smaller keys (e.g., split a large hash into sub-hashes).
- **Compress values** before storing (gzip, snappy, LZ4):
  ```python
  import zlib
  redis.set("key", zlib.compress(json.dumps(data).encode()))
  data = json.loads(zlib.decompress(redis.get("key")))
  ```
- **Use Redis data structures** instead of serialized blobs:
  - Use `HSET` for objects instead of `SET` with JSON.
  - Use `ZADD` for sorted data instead of large lists.
- **Set maxmemory policy** to evict large keys:
  ```bash
  redis-cli CONFIG SET maxmemory-policy allkeys-lru
  ```

---

## 3. Missing Expiration (Unbounded Growth)

Keys without TTLs accumulate indefinitely, growing memory usage without bound.

### Detect

```bash
# Check total keys and expired key stats
redis-cli INFO keyspace
redis-cli INFO stats | grep -E "expired_keys|evicted_keys"

# Count keys without TTL in a database
redis-cli --scan | while read key; do
  TTL=$(redis-cli TTL "$key")
  if [ "$TTL" = "-1" ]; then
    echo "NO TTL: $key"
  fi
done 2>/dev/null | head -50

# Quick count of persistent keys
redis-cli INFO keyspace
# Compare 'keys' vs 'expires' — large gap means many keys have no TTL
```

### Fix

- **Set TTL on all cache keys**: `redis-cli EXPIRE key 3600`
- **Use `SETEX` / `SET ... EX`** instead of plain `SET`:
  ```bash
  redis-cli SET mykey "value" EX 3600
  ```
- **Batch-fix existing keys without TTL**:
  ```bash
  redis-cli --scan | while read key; do
    TTL=$(redis-cli TTL "$key")
    if [ "$TTL" = "-1" ]; then
      redis-cli EXPIRE "$key" 86400  # 24h default
    fi
  done
  ```
- **Set a maxmemory policy** as a safety net:
  ```bash
  redis-cli CONFIG SET maxmemory 2gb
  redis-cli CONFIG SET maxmemory-policy allkeys-lru
  ```

---

## 4. Memory Fragmentation

High fragmentation ratio (>1.5) means Redis is using significantly more OS memory than its data requires.

### Detect

```bash
# Check fragmentation ratio
redis-cli INFO memory | grep mem_fragmentation_ratio
# Healthy: 1.0 - 1.5. Problematic: >1.5 or <1.0
```

### Fix

- **Enable active defragmentation** (Redis 4.0+):
  ```bash
  redis-cli CONFIG SET activedefrag yes
  redis-cli CONFIG SET active-defrag-threshold-lower 10
  redis-cli CONFIG SET active-defrag-threshold-upper 100
  ```
- **Restart Redis** if fragmentation is extreme — it reclaims memory on restart.
- **Use jemalloc** (default allocator) — avoid switching to libc malloc.

---

## 5. Unoptimized Data Structures

Using wrong Redis data types leads to wasted memory and CPU.

### Detect

```bash
# Check key types and sizes
redis-cli --scan | head -100 | while read key; do
  TYPE=$(redis-cli TYPE "$key")
  SIZE=$(redis-cli MEMORY USAGE "$key")
  echo "$key: type=$TYPE size=${SIZE}B"
done

# Check encoding (ziplist vs hashtable, etc.)
redis-cli OBJECT ENCODING key_name
# ziplist/listpack = memory-efficient; hashtable/skiplist = less efficient for small sets
```

### Fix

- **Keep hashes, sets, and lists small** to use memory-efficient encodings (ziplist/listpack).
- **Tune thresholds** in redis.conf:
  ```bash
  redis-cli CONFIG SET hash-max-listpack-entries 128
  redis-cli CONFIG SET hash-max-listpack-value 64
  redis-cli CONFIG SET list-max-listpack-size -2
  ```
- **Use hashes** instead of many top-level string keys for related data:
  ```bash
  # Instead of: SET user:1:name "Alice", SET user:1:email "a@b.com"
  # Use: HSET user:1 name "Alice" email "a@b.com"
  ```
- **Use Sorted Sets** for leaderboards/ranking instead of maintaining sorted lists in application code.

---

## 6. Idle Redis Instance

Redis running but serving no or minimal traffic.

### Detect

```bash
# Commands processed per second
redis-cli INFO stats | grep instantaneous_ops_per_sec

# Connected clients
redis-cli INFO clients | grep connected_clients

# Total commands processed
redis-cli INFO stats | grep total_commands_processed

# Check if keys exist at all
redis-cli DBSIZE
```

### Fix

- **Shut down** if no application depends on it.
- **Downsize** the instance (smaller memory, fewer replicas).
- **Switch to on-demand** (e.g., ElastiCache Serverless, Memorystore) if traffic is sporadic.
- **Consolidate** multiple low-traffic Redis instances into one using logical databases (`SELECT 0-15`).
