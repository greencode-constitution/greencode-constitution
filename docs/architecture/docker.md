# Docker Energy Antipatterns

Agent skill for detecting and fixing energy-wasting antipatterns in Docker and Docker Compose environments.

---

## 1. Idle Containers

Containers consuming resources with <1% CPU activity.

### Detect

```bash
# Snapshot of all container stats
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"

# Find idle containers (<1% CPU)
docker stats --no-stream --format '{{.Name}}\t{{.CPUPerc}}' | while read line; do
  NAME=$(echo "$line" | cut -f1)
  CPU=$(echo "$line" | cut -f2 | tr -d '%' | cut -d'.' -f1)
  if [ "${CPU:-0}" -lt 1 ]; then
    echo "IDLE: $NAME"
  fi
done
```

### Fix

- **Stop or remove** unused containers: `docker stop NAME && docker rm NAME`
- **Use `docker compose up --scale SERVICE=0`** for services not currently needed.
- **Implement health checks** so orchestrators can detect and restart stalled containers.
- **Schedule non-production** containers to shut down outside working hours via cron.

---

## 2. Containers Without Resource Limits

Containers with no memory/CPU limits can monopolize the host and waste energy via contention.

### Detect

```bash
# Containers without memory limits (Memory=0 means unlimited)
docker ps -q | xargs docker inspect --format '{{.Name}}: Memory={{.HostConfig.Memory}}' | grep "Memory=0"

# Containers without CPU limits
docker ps -q | xargs docker inspect --format '{{.Name}}: CPUQuota={{.HostConfig.CpuQuota}}' | grep "CPUQuota=0"

# In docker-compose files: search for missing limits
grep -rL "mem_limit\|memory:" --include="docker-compose*.yml" --include="docker-compose*.yaml" ./
grep -rL "cpus:\|cpu_shares:" --include="docker-compose*.yml" --include="docker-compose*.yaml" ./
```

### Fix

- **Add resource limits** in docker-compose:
  ```yaml
  services:
    myapp:
      deploy:
        resources:
          limits:
            cpus: '0.5'
            memory: 256M
          reservations:
            cpus: '0.1'
            memory: 128M
  ```
- **Use `docker update`** on running containers: `docker update --memory 256m --cpus 0.5 CONTAINER`
- **Set default runtime constraints** in `/etc/docker/daemon.json`:
  ```json
  { "default-ulimits": { "memlock": { "Name": "memlock", "Hard": -1, "Soft": -1 } } }
  ```

---

## 3. Bloated Container Images

Large images increase pull time, build time, storage, and startup energy cost.

### Detect

```bash
# List images sorted by size
docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}" | sort -k3 -h

# Find dangling/unused images
docker images -f "dangling=true" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"

# Check Dockerfile base image
grep -rn "^FROM" --include="Dockerfile*" ./
```

### Fix

- **Use Alpine-based images** (`node:alpine`, `python:slim`) instead of full distros.
- **Use multi-stage builds** to exclude build tools from the runtime image:
  ```dockerfile
  FROM node:20 AS build
  WORKDIR /app
  COPY . .
  RUN npm ci && npm run build

  FROM node:20-alpine
  COPY --from=build /app/dist ./dist
  CMD ["node", "dist/index.js"]
  ```
- **Add `.dockerignore`** to exclude `node_modules`, `.git`, tests, docs from the build context.
- **Clean up** dangling images: `docker image prune -f`
- **Clean up** unused images: `docker image prune -a`

---

## 4. Missing Health Checks

Containers without health checks run indefinitely even when stalled, wasting resources.

### Detect

```bash
# In docker-compose files
grep -rL "healthcheck:" --include="docker-compose*.yml" --include="docker-compose*.yaml" ./

# In Dockerfiles
grep -rL "HEALTHCHECK" --include="Dockerfile*" ./

# Running containers without health checks
docker ps --format '{{.Names}}' | while read NAME; do
  HC=$(docker inspect --format '{{.Config.Healthcheck}}' "$NAME" 2>/dev/null)
  if [ "$HC" == "<nil>" ]; then
    echo "NO HEALTHCHECK: $NAME"
  fi
done
```

### Fix

- **Add healthcheck in Dockerfile**:
  ```dockerfile
  HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1
  ```
- **Add healthcheck in docker-compose**:
  ```yaml
  services:
    myapp:
      healthcheck:
        test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
        interval: 30s
        timeout: 3s
        retries: 3
  ```

---

## 5. Missing Restart Policies

Containers without restart policies stay down after crashes, or restart endlessly without backoff.

### Detect

```bash
# In docker-compose files
grep -rL "restart:" --include="docker-compose*.yml" --include="docker-compose*.yaml" ./

# Running containers without restart policy
docker ps -q | xargs docker inspect --format '{{.Name}}: {{.HostConfig.RestartPolicy.Name}}' | grep ": no$\|: $"
```

### Fix

- **Set appropriate restart policy** in docker-compose:
  ```yaml
  services:
    myapp:
      restart: unless-stopped
  ```
- Options: `no`, `always`, `on-failure`, `unless-stopped`. Use `unless-stopped` for most services.

---

## 6. Stopped/Exited Containers and Dangling Volumes

Accumulation of exited containers and orphaned volumes wastes disk space.

### Detect

```bash
# Exited containers
docker ps -a --filter "status=exited" --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"

# Dangling volumes
docker volume ls -f dangling=true

# Disk usage summary
docker system df
```

### Fix

- **Remove exited containers**: `docker container prune -f`
- **Remove dangling volumes**: `docker volume prune -f`
- **Full cleanup**: `docker system prune -a --volumes` (removes all unused images, containers, volumes, networks)
- **Automate** by scheduling `docker system prune -f` via cron.

---

## 7. Inefficient Networking Between Containers

Containers communicating over the default bridge network instead of a dedicated network, or using host networking unnecessarily.

### Detect

```bash
# Check container network modes
docker ps -q | xargs docker inspect --format '{{.Name}}: {{.HostConfig.NetworkMode}}'

# High network I/O between containers
docker stats --no-stream --format "{{.Name}}: Net I/O {{.NetIO}}"
```

### Fix

- **Use dedicated Docker networks** for service groups:
  ```yaml
  networks:
    backend:
      driver: bridge
  services:
    api:
      networks: [backend]
    db:
      networks: [backend]
  ```
- **Use DNS names** instead of IP-based communication.
- **Avoid host networking** unless strictly required for performance.
- **Consider using Unix sockets** for co-located services for zero network overhead.
