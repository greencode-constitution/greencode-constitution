# Kubernetes Energy Antipatterns

Agent skill for detecting and fixing energy-wasting antipatterns in Kubernetes clusters.

---

## 1. Underutilized Nodes

Nodes running at <20% CPU, wasting energy on idle hardware.

### Detect

```bash
# Node resource usage
kubectl top nodes

# Find nodes under 20% CPU
kubectl top nodes --no-headers | while read line; do
  NAME=$(echo $line | awk '{print $1}')
  CPU_PCT=$(echo $line | awk '{print $3}' | tr -d '%')
  if [ "${CPU_PCT:-100}" -lt 20 ]; then
    MEM_PCT=$(echo $line | awk '{print $5}')
    echo "UNDERUTILIZED: $NAME — CPU ${CPU_PCT}%, Mem $MEM_PCT"
  fi
done

# Node capacity vs allocatable
kubectl get nodes -o custom-columns=\
NAME:.metadata.name,\
CPU_CAP:.status.capacity.cpu,\
CPU_ALLOC:.status.allocatable.cpu,\
MEM_CAP:.status.capacity.memory,\
MEM_ALLOC:.status.allocatable.memory
```

### Fix

- **Enable Cluster Autoscaler** to remove empty/underutilized nodes automatically.
- **Use `MostAllocated` scheduling strategy** to pack pods onto fewer nodes:
  ```yaml
  # KubeSchedulerConfiguration
  profiles:
  - schedulerName: default-scheduler
    plugins:
      score:
        enabled:
        - name: NodeResourcesFit
    pluginConfig:
    - name: NodeResourcesFit
      args:
        scoringStrategy:
          type: MostAllocated
  ```
- **Consolidate workloads** onto fewer, right-sized node pools.
- **Use Arm-based nodes** (e.g., AWS Graviton, GCP Tau T2A) for better perf/watt.

---

## 2. Over-Provisioned Pods

Pods requesting far more CPU/memory than they actually use (typically 8x gap).

### Detect

```bash
# Compare actual vs requested
kubectl top pods --all-namespaces --no-headers | while read line; do
  NS=$(echo $line | awk '{print $1}')
  POD=$(echo $line | awk '{print $2}')
  CPU_USED=$(echo $line | awk '{print $3}' | tr -d 'm')
  CPU_REQ=$(kubectl get pod $POD -n $NS -o jsonpath='{.spec.containers[0].resources.requests.cpu}' 2>/dev/null | tr -d 'm')
  if [ ! -z "$CPU_REQ" ] && [ "$CPU_REQ" -gt 0 ] 2>/dev/null; then
    UTIL=$((CPU_USED * 100 / CPU_REQ))
    if [ "$UTIL" -lt 20 ]; then
      echo "OVER-PROVISIONED: $NS/$POD — using ${CPU_USED}m of ${CPU_REQ}m (${UTIL}%)"
    fi
  fi
done

# Use Robusta KRR for Prometheus-based recommendations
# pip install robusta-krr
krr simple
```

### Fix

- **Lower resource requests** to match p95 actual usage (keep limits as safety cap).
- **Deploy Vertical Pod Autoscaler (VPA)** in recommendation or auto mode:
  ```yaml
  apiVersion: autoscaling.k8s.io/v1
  kind: VerticalPodAutoscaler
  metadata:
    name: my-app-vpa
  spec:
    targetRef:
      apiVersion: apps/v1
      kind: Deployment
      name: my-app
    updatePolicy:
      updateMode: "Auto"
  ```
- **Use Robusta KRR** to generate rightsizing recommendations from Prometheus data.
- **Profile with load testing** (k6, Locust) to find actual resource needs under realistic load.

---

## 3. Pods Without Resource Limits

Pods missing requests/limits allow noisy neighbors and prevent efficient scheduling.

### Detect

```bash
# Pods without CPU limits
kubectl get pods --all-namespaces -o json | jq -r '
  .items[] |
  select(.spec.containers[].resources.limits.cpu == null) |
  "\(.metadata.namespace)/\(.metadata.name)"'

# Pods without memory limits
kubectl get pods --all-namespaces -o json | jq -r '
  .items[] |
  select(.spec.containers[].resources.limits.memory == null) |
  "\(.metadata.namespace)/\(.metadata.name)"'

# Pods without any requests
kubectl get pods --all-namespaces -o json | jq -r '
  .items[] |
  select(.spec.containers[].resources.requests == null) |
  "\(.metadata.namespace)/\(.metadata.name)"'
```

### Fix

- **Add resource requests and limits** to all containers in deployment specs.
- **Set LimitRanges** per namespace as defaults:
  ```yaml
  apiVersion: v1
  kind: LimitRange
  metadata:
    name: default-limits
    namespace: my-ns
  spec:
    limits:
    - default:
        cpu: "500m"
        memory: "256Mi"
      defaultRequest:
        cpu: "100m"
        memory: "128Mi"
      type: Container
  ```
- **Set ResourceQuotas** per namespace to cap total consumption.
- **Use admission controllers** or OPA/Gatekeeper to enforce resource requirements.

---

## 4. Chatty Microservices

Services making excessive inter-service calls (>1000 RPS between any pair).

### Detect

```bash
# With Istio — query Prometheus for inter-service traffic
curl -s 'http://PROMETHEUS:9090/api/v1/query' \
  --data-urlencode 'query=sum(rate(istio_requests_total[5m])) by (source_app, destination_app) > 1000' \
  | jq '.data.result'

# P99 latency between services
curl -s 'http://PROMETHEUS:9090/api/v1/query' \
  --data-urlencode 'query=histogram_quantile(0.99, sum(rate(istio_request_duration_milliseconds_bucket[5m])) by (source_app, destination_app, le))' \
  | jq '.data.result'

# Envoy sidecar stats (per pod)
kubectl exec POD -c istio-proxy -n NS -- \
  curl -s localhost:15000/stats | grep "cluster.*upstream_rq_completed"
```

### Fix

- **Introduce caching** (Redis/Memcached) between frequently communicating services.
- **Batch API calls** — combine multiple small requests into a single bulk endpoint.
- **Use async messaging** (Kafka, NATS, RabbitMQ) instead of synchronous HTTP for non-critical paths.
- **Implement gRPC** instead of REST for internal service-to-service — lower overhead per call.
- **Merge tightly coupled services** that always call each other back into a single service.

---

## 5. Stale HPA Configuration

HPAs stuck at minReplicas, never scaling, or misconfigured.

### Detect

```bash
# List all HPAs
kubectl get hpa --all-namespaces

# Find HPAs stuck at min
kubectl get hpa --all-namespaces -o json | jq -r '
  .items[] |
  select(.status.currentReplicas == .spec.minReplicas) |
  "\(.metadata.namespace)/\(.metadata.name): stuck at min=\(.spec.minReplicas)"'

# Detailed status
kubectl describe hpa HPA_NAME -n NAMESPACE
```

### Fix

- **Lower minReplicas** if the service can tolerate it.
- **Add scale-down policies** to react faster:
  ```yaml
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 120
      policies:
      - type: Percent
        value: 50
        periodSeconds: 60
  ```
- **Use KEDA** for event-driven autoscaling (scale to zero for queue-based workloads).
- **Use custom metrics** instead of just CPU (e.g., request rate, queue depth).

---

## 6. Unoptimized Sidecars & Init Containers

Sidecars and init containers with inflated resource requests.

### Detect

```bash
# List pods with sidecars (multi-container pods)
kubectl get pods --all-namespaces -o json | jq -r '
  .items[] |
  select(.spec.containers | length > 1) |
  "\(.metadata.namespace)/\(.metadata.name): \(.spec.containers | length) containers"'

# Check sidecar resource requests
kubectl get pods --all-namespaces -o json | jq -r '
  .items[] |
  select(.spec.containers | length > 1) |
  .spec.containers[] |
  select(.name != .name) |
  "\(.name): cpu=\(.resources.requests.cpu // "none"), mem=\(.resources.requests.memory // "none")"'
```

### Fix

- **Rightsize sidecar requests** to match actual usage observed via `kubectl top pod POD --containers`.
- **Use Istio ambient mode** (no sidecar proxy) to eliminate per-pod Envoy overhead.
- **Set init container resources** separately and lower than main container (they run sequentially).

---

## 7. Missing Prometheus Alerting for Waste

No alerts configured to flag energy waste patterns.

### Detect

```bash
# Check if Prometheus rules exist for efficiency
curl -s 'http://PROMETHEUS:9090/api/v1/rules' | jq '.data.groups[].rules[].name' | grep -i "idle\|underutilized\|overprovisioned"
```

### Fix

Add alerting rules:

```yaml
groups:
- name: energy-efficiency
  rules:
  - alert: NodeUnderutilized
    expr: 100 - (avg by (instance) (irate(node_cpu_seconds_total{mode="idle"}[1h])) * 100) < 15
    for: 24h
    annotations:
      summary: "Node {{ $labels.instance }} <15% CPU for 24h"
  - alert: PodOverProvisioned
    expr: |
      sum(rate(container_cpu_usage_seconds_total{container!=""}[1h])) by (pod, namespace)
      / sum(kube_pod_container_resource_requests{resource="cpu"}) by (pod, namespace) < 0.1
    for: 24h
    annotations:
      summary: "{{ $labels.namespace }}/{{ $labels.pod }} using <10% of requested CPU"
  - alert: ChattyServices
    expr: sum(rate(istio_requests_total[5m])) by (source_app, destination_app) > 5000
    for: 1h
    annotations:
      summary: "High traffic: {{ $labels.source_app }} → {{ $labels.destination_app }}"
```

---

## 8. Always-On Dev/Test Workloads

Dev, staging, and test namespaces running 24/7 when only used during business hours.

### Detect

```bash
# List non-production namespaces
kubectl get namespaces | grep -iE 'dev|staging|test|qa|uat|sandbox|preview'

# Check if non-prod workloads run off-hours (run this outside business hours)
for NS in $(kubectl get namespaces -o name | grep -iE 'dev|staging|test|qa|uat'); do
  PODS=$(kubectl get pods -n ${NS#namespace/} --no-headers 2>/dev/null | wc -l)
  if [ "$PODS" -gt 0 ]; then
    echo "RUNNING OFF-HOURS: ${NS#namespace/} — $PODS pods"
  fi
done

# Check for KEDA ScaledObjects or CronJobs that handle scale-down
kubectl get scaledobjects --all-namespaces 2>/dev/null || echo "KEDA not installed"
```

### Fix

- **Use `kube-downscaler`** to automatically scale non-prod to zero outside business hours:
  ```bash
  # Annotate namespace for downscaling
  kubectl annotate namespace dev downscaler/uptime="Mon-Fri 08:00-20:00 UTC"
  ```
- **Use KEDA Cron scaler** to schedule scale-to-zero:
  ```yaml
  apiVersion: keda.sh/v1alpha1
  kind: ScaledObject
  metadata:
    name: dev-scaler
    namespace: dev
  spec:
    scaleTargetRef:
      name: my-app
    minReplicaCount: 0
    triggers:
    - type: cron
      metadata:
        timezone: UTC
        start: "0 8 * * 1-5"
        end: "0 20 * * 1-5"
        desiredReplicas: "2"
  ```
- **Use ephemeral namespaces** created on demand by CI/CD and destroyed after testing.

---

## 9. Time-Fixed CronJobs (No Carbon-Aware Scheduling)

CronJobs scheduled at fixed times run regardless of grid carbon intensity. Shifting flexible batch work to low-carbon periods reduces emissions without code changes.

### Detect

```bash
# List all CronJobs
kubectl get cronjobs --all-namespaces \
  -o custom-columns=NAMESPACE:.metadata.namespace,NAME:.metadata.name,SCHEDULE:.spec.schedule,SUSPEND:.spec.suspend

# Find CronJobs without carbon-aware annotations
kubectl get cronjobs --all-namespaces -o json | jq -r '
  .items[] |
  select(.metadata.annotations["carbon-aware"] == null) |
  "\(.metadata.namespace)/\(.metadata.name): \(.spec.schedule)"'
```

### Fix

- **Integrate carbon-intensity APIs** (WattTime, Electricity Maps) into scheduling decisions.
- **Use KEDA with carbon-aware triggers** or a controller that adjusts CronJob schedules based on 24-hour carbon forecasts.
- **Add flexible deadline windows** — instead of "run at 2am", allow "run between midnight and 6am when carbon intensity is lowest."
- **Label flexible vs fixed jobs** so schedulers know which jobs can be shifted:
  ```bash
  kubectl annotate cronjob CRONJOB_NAME carbon-aware=true flexible-window=6h
  ```

---

## 10. Missing NetworkPolicies

Without NetworkPolicies, all pods can communicate with all other pods. This allows unnecessary network traffic and increases attack surface — compromised pods waste energy via unauthorized activity.

### Detect

```bash
# Check if any NetworkPolicies exist
kubectl get networkpolicies --all-namespaces

# Count namespaces without any NetworkPolicy
for NS in $(kubectl get namespaces -o name); do
  COUNT=$(kubectl get networkpolicies -n ${NS#namespace/} --no-headers 2>/dev/null | wc -l)
  if [ "$COUNT" -eq 0 ]; then
    echo "NO NETWORK POLICY: ${NS#namespace/}"
  fi
done
```

### Fix

- **Add a default-deny ingress policy** per namespace and then whitelist required traffic:
  ```yaml
  apiVersion: networking.k8s.io/v1
  kind: NetworkPolicy
  metadata:
    name: default-deny-ingress
    namespace: production
  spec:
    podSelector: {}
    policyTypes:
    - Ingress
  ```
- **Allow only required communication** between services:
  ```yaml
  apiVersion: networking.k8s.io/v1
  kind: NetworkPolicy
  metadata:
    name: allow-api-to-db
    namespace: production
  spec:
    podSelector:
      matchLabels:
        app: database
    ingress:
    - from:
      - podSelector:
          matchLabels:
            app: api
      ports:
      - port: 5432
  ```
- **Use a CNI that supports NetworkPolicies** (Calico, Cilium, Weave Net).
- **Add egress policies** to prevent pods from reaching unauthorized external services.
