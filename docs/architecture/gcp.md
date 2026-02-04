# GCP Energy Antipatterns

Agent skill for detecting and fixing energy-wasting antipatterns in Google Cloud infrastructure.

---

## 1. Idle VM Instances

VMs running with minimal CPU/memory utilization over extended periods.

### Detect

```bash
# List running instances
gcloud compute instances list \
  --filter="status=RUNNING" \
  --format="table(name,zone,machineType,status,creationTimestamp)"

# Get idle VM recommendations (all zones)
for ZONE in $(gcloud compute zones list --format="value(name)"); do
  gcloud recommender recommendations list \
    --project=PROJECT_ID --location=$ZONE \
    --recommender=google.compute.instance.IdleResourceRecommender \
    --format="table(name,description,primaryImpact.costProjection.cost.units)" 2>/dev/null
done

# CPU usage insights
gcloud recommender insights list \
  --project=PROJECT_ID --location=ZONE \
  --insight-type=google.compute.instance.CpuUsageInsight \
  --format="yaml"
```

### Fix

- **Delete** confirmed idle VMs.
- **Apply rightsizing recommendations**:
  ```bash
  gcloud recommender recommendations list \
    --project=PROJECT_ID --location=ZONE \
    --recommender=google.compute.instance.MachineTypeRecommender \
    --format="table(name,description,stateInfo.state)"
  ```
- **Switch to E2 or Tau T2A** (Arm-based) machine types for better energy efficiency.
- **Use preemptible/spot VMs** for fault-tolerant workloads.
- **Schedule auto-start/stop** for dev/staging environments using Instance Schedules.

---

## 2. Idle Disks & Unused IPs

Unattached persistent disks and reserved-but-unused static IPs.

### Detect

```bash
# Unattached disks
gcloud compute disks list \
  --filter="NOT users:*" \
  --format="table(name,zone,sizeGb,status,creationTimestamp)"

# Idle disk recommendations
gcloud recommender recommendations list \
  --project=PROJECT_ID --location=ZONE \
  --recommender=google.compute.disk.IdleResourceRecommender \
  --format="table(name,description,primaryImpact.costProjection.cost.units)"

# Unused static IPs
gcloud compute addresses list \
  --filter="status=RESERVED" \
  --format="table(name,address,region,status)"
```

### Fix

- **Snapshot** important disks, then **delete**: `gcloud compute disks delete DISK_NAME --zone=ZONE`
- **Release** unused IPs: `gcloud compute addresses delete IP_NAME --region=REGION`
- **Downgrade disk types** — use `pd-standard` instead of `pd-ssd` for low-IOPS workloads.
- **Set lifecycle policies** on snapshots to auto-delete after retention period.

---

## 3. Underutilized VMs (Over-Provisioned)

VMs with machine types far exceeding actual workload requirements.

### Detect

```bash
# Rightsizing recommendations
gcloud recommender recommendations list \
  --project=PROJECT_ID --location=ZONE \
  --recommender=google.compute.instance.MachineTypeRecommender \
  --format="table(name,description,stateInfo.state)"

# CPU usage insights
gcloud recommender insights list \
  --project=PROJECT_ID --location=ZONE \
  --insight-type=google.compute.instance.CpuUsageInsight \
  --format="yaml"
```

### Fix

- **Resize** VMs: `gcloud compute instances set-machine-type INSTANCE --machine-type=e2-medium --zone=ZONE` (requires stop first).
- **Use custom machine types** to match exact CPU/memory needs instead of predefined sizes.
- **Enable autoscaling** on managed instance groups instead of over-provisioning for peak.
- **Migrate to Tau T2A** (Arm) for batch/scale-out workloads — better performance per watt.

---

## 4. Idle Cloud Functions

Functions with zero executions over 30+ days.

### Detect

```bash
# List all functions
gcloud functions list --format="table(name,runtime,status,updateTime)"

# Execution count (30 days)
gcloud monitoring time-series list \
  --filter='metric.type="cloudfunctions.googleapis.com/function/execution_count"' \
  --start-time=$(date -u -d '30 days ago' +%Y-%m-%dT%H:%M:%SZ) \
  --end-time=$(date -u +%Y-%m-%dT%H:%M:%SZ)
```

### Fix

- **Delete** unused functions: `gcloud functions delete FUNCTION_NAME`
- **Reduce min instances** to 0 for low-traffic functions (allows scale-to-zero).
- **Lower memory allocation** to match actual usage.
- **Migrate to Cloud Run** for services that need longer execution times — Cloud Run scales to zero.

---

## 5. Idle Cloud Run Services

Services receiving zero traffic.

### Detect

```bash
# List services
gcloud run services list \
  --format="table(metadata.name,status.url,status.conditions[0].status)"

# Request count (7 days)
gcloud monitoring time-series list \
  --filter='metric.type="run.googleapis.com/request_count"' \
  --start-time=$(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%SZ) \
  --end-time=$(date -u +%Y-%m-%dT%H:%M:%SZ)
```

### Fix

- **Delete** unused services: `gcloud run services delete SERVICE_NAME`
- **Set min instances to 0** so the service scales to zero when idle.
- **Set CPU allocation to "request-based"** (CPU only allocated during request processing).
- **Lower concurrency** to match actual load and reduce per-instance resource waste.

---

## 6. Unattended Projects

Entire GCP projects consuming resources with no active usage.

### Detect

```bash
# List projects
gcloud projects list --format="table(projectId,name,createTime)"

# Use Active Assist Unattended Project Recommender
gcloud recommender recommendations list \
  --project=PROJECT_ID --location=global \
  --recommender=google.resourcemanager.projectUtilization.Recommender \
  --format="table(name,description)" 2>/dev/null
```

### Fix

- **Shut down** confirmed unused projects: `gcloud projects delete PROJECT_ID`
- **Export billing to BigQuery** and set up alerts for low-activity projects.
- **Use the Carbon Footprint dashboard** to track and reduce emissions per project.
