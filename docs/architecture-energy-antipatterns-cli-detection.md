# Architecture-Level Energy Anti-Patterns: CLI Detection Guide

> Command-line tools and queries for detecting architectural energy anti-patterns across AWS, Google Cloud, Kubernetes, and Docker Compose environments

---

## Table of Contents

1. [Overview](#overview)
2. [AWS CLI Detection Commands](#aws-cli-detection-commands)
3. [Google Cloud CLI Detection Commands](#google-cloud-cli-detection-commands)
4. [Kubernetes Detection Commands](#kubernetes-detection-commands)
5. [Docker / Docker Compose Detection Commands](#docker--docker-compose-detection-commands)
6. [Prometheus / PromQL Queries](#prometheus--promql-queries)
7. [Database Query Analysis](#database-query-analysis)
8. [Infrastructure-as-Code Static Analysis](#infrastructure-as-code-static-analysis)
9. [Automated Detection Scripts](#automated-detection-scripts)
10. [Sources](#sources)

---

## Overview

Unlike code-level anti-patterns that can be detected with grep/regex, architectural anti-patterns require:
- **Metrics analysis** — CPU, memory, network utilization over time
- **Service dependency mapping** — understanding inter-service communication
- **Cost and resource auditing** — identifying idle or over-provisioned resources
- **Traffic pattern analysis** — detecting chatty microservices

This document provides CLI commands organized by infrastructure type.

### Anti-Patterns Covered

| Anti-Pattern | Detection Method |
|--------------|------------------|
| Idle/underutilized resources | Cloud provider CLIs, metrics queries |
| Over-provisioned infrastructure | Resource utilization vs. allocation |
| Chatty microservices | Service mesh metrics, network I/O |
| Missing caching layers | Database query analysis, cache hit ratios |
| Serverless cold starts | Lambda/Cloud Functions metrics |
| Inefficient data transfer | Network metrics, payload size analysis |

---

## AWS CLI Detection Commands

### Prerequisites

```bash
# Install and configure AWS CLI
pip install awscli
aws configure

# Verify access
aws sts get-caller-identity
```

---

### 1. Detecting Idle EC2 Instances

**Definition**: EC2 instances with CPU utilization < 10% and network I/O < 5 MB for extended periods.

#### List All Running Instances

```bash
# List all running EC2 instances with instance type and launch time
aws ec2 describe-instances \
  --filters "Name=instance-state-name,Values=running" \
  --query 'Reservations[*].Instances[*].[InstanceId,InstanceType,LaunchTime,Tags[?Key==`Name`].Value|[0]]' \
  --output table
```

#### Get CPU Utilization for Specific Instance (Last 7 Days)

```bash
# Replace INSTANCE_ID with your instance ID
aws cloudwatch get-metric-statistics \
  --namespace AWS/EC2 \
  --metric-name CPUUtilization \
  --dimensions Name=InstanceId,Value=INSTANCE_ID \
  --start-time $(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%SZ) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --period 86400 \
  --statistics Average Maximum \
  --output table
```

#### Batch Script: Find All Underutilized Instances

```bash
#!/bin/bash
# find-idle-ec2.sh - Find EC2 instances with avg CPU < 10% over 7 days

THRESHOLD=10
PERIOD_DAYS=7

echo "Instance ID | Avg CPU % | Max CPU % | Instance Type"
echo "-------------------------------------------------------"

for INSTANCE_ID in $(aws ec2 describe-instances \
  --filters "Name=instance-state-name,Values=running" \
  --query 'Reservations[*].Instances[*].InstanceId' \
  --output text); do
  
  STATS=$(aws cloudwatch get-metric-statistics \
    --namespace AWS/EC2 \
    --metric-name CPUUtilization \
    --dimensions Name=InstanceId,Value=$INSTANCE_ID \
    --start-time $(date -u -d "${PERIOD_DAYS} days ago" +%Y-%m-%dT%H:%M:%SZ) \
    --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
    --period $((PERIOD_DAYS * 86400)) \
    --statistics Average Maximum \
    --query 'Datapoints[0].[Average,Maximum]' \
    --output text 2>/dev/null)
  
  AVG_CPU=$(echo $STATS | awk '{printf "%.2f", $1}')
  MAX_CPU=$(echo $STATS | awk '{printf "%.2f", $2}')
  
  if (( $(echo "$AVG_CPU < $THRESHOLD" | bc -l) )); then
    INSTANCE_TYPE=$(aws ec2 describe-instances \
      --instance-ids $INSTANCE_ID \
      --query 'Reservations[0].Instances[0].InstanceType' \
      --output text)
    echo "$INSTANCE_ID | $AVG_CPU | $MAX_CPU | $INSTANCE_TYPE"
  fi
done
```

#### Get Network I/O Metrics

```bash
# Network In (bytes) - last 7 days
aws cloudwatch get-metric-statistics \
  --namespace AWS/EC2 \
  --metric-name NetworkIn \
  --dimensions Name=InstanceId,Value=INSTANCE_ID \
  --start-time $(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%SZ) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --period 86400 \
  --statistics Sum \
  --output table

# Network Out (bytes) - last 7 days
aws cloudwatch get-metric-statistics \
  --namespace AWS/EC2 \
  --metric-name NetworkOut \
  --dimensions Name=InstanceId,Value=INSTANCE_ID \
  --start-time $(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%SZ) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --period 86400 \
  --statistics Sum \
  --output table
```

---

### 2. Detecting Stopped Instances with Attached Resources

**Problem**: Stopped instances still incur costs for attached EBS volumes, Elastic IPs, etc.

```bash
# Find stopped instances older than 7 days
aws ec2 describe-instances \
  --filters "Name=instance-state-name,Values=stopped" \
  --query 'Reservations[*].Instances[?LaunchTime<=`'$(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%SZ)'`].[InstanceId,InstanceType,LaunchTime,BlockDeviceMappings[*].Ebs.VolumeId]' \
  --output table

# Find unattached EBS volumes
aws ec2 describe-volumes \
  --filters "Name=status,Values=available" \
  --query 'Volumes[*].[VolumeId,Size,CreateTime,VolumeType]' \
  --output table

# Find unassociated Elastic IPs (these incur charges)
aws ec2 describe-addresses \
  --query 'Addresses[?AssociationId==`null`].[PublicIp,AllocationId]' \
  --output table
```

---

### 3. Detecting Idle Load Balancers

```bash
# List all Application Load Balancers
aws elbv2 describe-load-balancers \
  --query 'LoadBalancers[*].[LoadBalancerName,LoadBalancerArn,State.Code]' \
  --output table

# Check for ALBs with no healthy targets
for ALB_ARN in $(aws elbv2 describe-load-balancers \
  --query 'LoadBalancers[*].LoadBalancerArn' --output text); do
  
  echo "=== $(basename $ALB_ARN) ==="
  
  # Get target groups for this ALB
  for TG_ARN in $(aws elbv2 describe-target-groups \
    --load-balancer-arn $ALB_ARN \
    --query 'TargetGroups[*].TargetGroupArn' --output text); do
    
    # Check target health
    aws elbv2 describe-target-health \
      --target-group-arn $TG_ARN \
      --query 'TargetHealthDescriptions[*].[Target.Id,TargetHealth.State]' \
      --output table
  done
done

# Get ALB request count (last 7 days) - idle if zero
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApplicationELB \
  --metric-name RequestCount \
  --dimensions Name=LoadBalancer,Value=app/ALB_NAME/LOAD_BALANCER_ID \
  --start-time $(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%SZ) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --period 86400 \
  --statistics Sum \
  --output table
```

---

### 4. Detecting Idle RDS Instances

```bash
# List all RDS instances
aws rds describe-db-instances \
  --query 'DBInstances[*].[DBInstanceIdentifier,DBInstanceClass,DBInstanceStatus,Engine]' \
  --output table

# Get database connections (last 7 days) - idle if consistently zero
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name DatabaseConnections \
  --dimensions Name=DBInstanceIdentifier,Value=DB_INSTANCE_ID \
  --start-time $(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%SZ) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --period 86400 \
  --statistics Average Maximum \
  --output table

# Get CPU utilization for RDS
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name CPUUtilization \
  --dimensions Name=DBInstanceIdentifier,Value=DB_INSTANCE_ID \
  --start-time $(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%SZ) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --period 86400 \
  --statistics Average \
  --output table
```

---

### 5. Detecting Lambda Cold Starts and Idle Functions

#### Find Functions with Zero Invocations

```bash
# List all Lambda functions
aws lambda list-functions \
  --query 'Functions[*].[FunctionName,Runtime,MemorySize,LastModified]' \
  --output table

# Check invocations for a function (last 30 days)
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=FUNCTION_NAME \
  --start-time $(date -u -d '30 days ago' +%Y-%m-%dT%H:%M:%SZ) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --period 2592000 \
  --statistics Sum \
  --output table
```

#### Batch: Find All Unused Lambda Functions

```bash
#!/bin/bash
# find-unused-lambdas.sh - Find Lambda functions with 0 invocations in last 30 days

echo "Function Name | Invocations (30d) | Memory (MB) | Runtime"
echo "-----------------------------------------------------------"

for FUNC in $(aws lambda list-functions --query 'Functions[*].FunctionName' --output text); do
  INVOCATIONS=$(aws cloudwatch get-metric-statistics \
    --namespace AWS/Lambda \
    --metric-name Invocations \
    --dimensions Name=FunctionName,Value=$FUNC \
    --start-time $(date -u -d '30 days ago' +%Y-%m-%dT%H:%M:%SZ) \
    --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
    --period 2592000 \
    --statistics Sum \
    --query 'Datapoints[0].Sum' \
    --output text 2>/dev/null)
  
  if [ "$INVOCATIONS" == "None" ] || [ -z "$INVOCATIONS" ] || [ "$INVOCATIONS" == "0.0" ]; then
    INFO=$(aws lambda get-function-configuration \
      --function-name $FUNC \
      --query '[MemorySize,Runtime]' \
      --output text)
    echo "$FUNC | 0 | $INFO"
  fi
done
```

#### Analyze Cold Starts with CloudWatch Logs Insights

```bash
# Query Lambda logs for cold starts (requires CloudWatch Logs Insights)
aws logs start-query \
  --log-group-name "/aws/lambda/FUNCTION_NAME" \
  --start-time $(date -u -d '7 days ago' +%s) \
  --end-time $(date -u +%s) \
  --query-string 'filter @type = "REPORT" | stats count(*) as invocations, count(@initDuration) as coldStarts, avg(@initDuration) as avgColdStartMs by bin(1h)'

# Get query results (use query-id from above)
aws logs get-query-results --query-id QUERY_ID
```

---

### 6. Detecting NAT Gateway Idle Usage

```bash
# List NAT Gateways
aws ec2 describe-nat-gateways \
  --query 'NatGateways[*].[NatGatewayId,State,SubnetId,CreateTime]' \
  --output table

# Check bytes transferred (idle if zero)
aws cloudwatch get-metric-statistics \
  --namespace AWS/NATGateway \
  --metric-name BytesOutToDestination \
  --dimensions Name=NatGatewayId,Value=NAT_GATEWAY_ID \
  --start-time $(date -u -d '14 days ago' +%Y-%m-%dT%H:%M:%SZ) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --period 86400 \
  --statistics Sum \
  --output table
```

---

### 7. Using AWS Compute Optimizer (CLI)

```bash
# Enable Compute Optimizer (if not already)
aws compute-optimizer update-enrollment-status --status Active

# Get EC2 instance recommendations
aws compute-optimizer get-ec2-instance-recommendations \
  --query 'instanceRecommendations[*].[instanceArn,finding,currentInstanceType,recommendationOptions[0].instanceType]' \
  --output table

# Get Lambda function recommendations
aws compute-optimizer get-lambda-function-recommendations \
  --query 'lambdaFunctionRecommendations[*].[functionArn,finding,currentMemorySize,memorySizeRecommendationOptions[0].memorySize]' \
  --output table

# Get EBS volume recommendations
aws compute-optimizer get-ebs-volume-recommendations \
  --query 'volumeRecommendations[*].[volumeArn,finding,currentConfiguration.volumeType,volumeRecommendationOptions[0].configuration.volumeType]' \
  --output table
```

---

## Google Cloud CLI Detection Commands

### Prerequisites

```bash
# Install and configure gcloud CLI
curl https://sdk.cloud.google.com | bash
gcloud init
gcloud auth login

# Set project
gcloud config set project PROJECT_ID
```

---

### 1. Detecting Idle VM Instances

```bash
# List all running VM instances
gcloud compute instances list \
  --filter="status=RUNNING" \
  --format="table(name,zone,machineType,status,creationTimestamp)"

# Get idle VM recommendations (built-in feature)
gcloud recommender recommendations list \
  --project=PROJECT_ID \
  --location=ZONE \
  --recommender=google.compute.instance.IdleResourceRecommender \
  --format="table(name,description,primaryImpact.costProjection.cost.units)"

# List recommendations for all zones
for ZONE in $(gcloud compute zones list --format="value(name)"); do
  echo "=== Zone: $ZONE ==="
  gcloud recommender recommendations list \
    --project=PROJECT_ID \
    --location=$ZONE \
    --recommender=google.compute.instance.IdleResourceRecommender \
    --format="table(name,description)" 2>/dev/null
done
```

---

### 2. Detecting Idle Disks and Resources

```bash
# Get idle persistent disk recommendations
gcloud recommender recommendations list \
  --project=PROJECT_ID \
  --location=ZONE \
  --recommender=google.compute.disk.IdleResourceRecommender \
  --format="table(name,description,primaryImpact.costProjection.cost.units)"

# Find unattached disks
gcloud compute disks list \
  --filter="NOT users:*" \
  --format="table(name,zone,sizeGb,status,creationTimestamp)"

# Find unused static IPs
gcloud compute addresses list \
  --filter="status=RESERVED" \
  --format="table(name,address,region,status)"
```

---

### 3. Detecting Underutilized VM Instances

```bash
# Get machine type recommendations (rightsizing)
gcloud recommender recommendations list \
  --project=PROJECT_ID \
  --location=ZONE \
  --recommender=google.compute.instance.MachineTypeRecommender \
  --format="table(name,description,stateInfo.state)"

# View VM instance insights (CPU/memory usage patterns)
gcloud recommender insights list \
  --project=PROJECT_ID \
  --location=ZONE \
  --insight-type=google.compute.instance.CpuUsageInsight \
  --format="yaml"
```

---

### 4. Cloud Functions Metrics

```bash
# List all Cloud Functions
gcloud functions list \
  --format="table(name,runtime,status,updateTime)"

# Get function execution count (requires Monitoring API)
gcloud monitoring time-series list \
  --filter='metric.type="cloudfunctions.googleapis.com/function/execution_count"' \
  --start-time=$(date -u -d '30 days ago' +%Y-%m-%dT%H:%M:%SZ) \
  --end-time=$(date -u +%Y-%m-%dT%H:%M:%SZ)
```

---

### 5. Cloud Run Idle Services

```bash
# List Cloud Run services
gcloud run services list \
  --format="table(metadata.name,status.url,status.conditions[0].status)"

# Get request count metrics
gcloud monitoring time-series list \
  --filter='metric.type="run.googleapis.com/request_count"' \
  --start-time=$(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%SZ) \
  --end-time=$(date -u +%Y-%m-%dT%H:%M:%SZ)
```

---

## Kubernetes Detection Commands

### Prerequisites

```bash
# Ensure kubectl is configured
kubectl cluster-info

# Install metrics-server if not present
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

# Verify metrics-server is running
kubectl get pods -n kube-system | grep metrics-server
```

---

### 1. Detecting Underutilized Nodes

```bash
# View node resource usage
kubectl top nodes

# Detailed node usage with percentages
kubectl top nodes --no-headers | while read line; do
  NAME=$(echo $line | awk '{print $1}')
  CPU=$(echo $line | awk '{print $2}')
  CPU_PCT=$(echo $line | awk '{print $3}')
  MEM=$(echo $line | awk '{print $4}')
  MEM_PCT=$(echo $line | awk '{print $5}')
  echo "Node: $NAME | CPU: $CPU ($CPU_PCT) | Memory: $MEM ($MEM_PCT)"
done

# Get node capacity and allocatable resources
kubectl get nodes -o custom-columns=\
NAME:.metadata.name,\
CPU_CAPACITY:.status.capacity.cpu,\
CPU_ALLOCATABLE:.status.allocatable.cpu,\
MEM_CAPACITY:.status.capacity.memory,\
MEM_ALLOCATABLE:.status.allocatable.memory
```

#### Find Underutilized Nodes Script

```bash
#!/bin/bash
# find-underutilized-nodes.sh - Find nodes with < 20% CPU utilization

THRESHOLD=20

echo "Underutilized Nodes (CPU < ${THRESHOLD}%):"
echo "==========================================="

kubectl top nodes --no-headers | while read line; do
  NAME=$(echo $line | awk '{print $1}')
  CPU_PCT=$(echo $line | awk '{print $3}' | tr -d '%')
  
  if [ "$CPU_PCT" -lt "$THRESHOLD" ]; then
    MEM_PCT=$(echo $line | awk '{print $5}')
    echo "$NAME: CPU ${CPU_PCT}%, Memory $MEM_PCT"
  fi
done
```

---

### 2. Detecting Underutilized Pods

```bash
# View pod resource usage (all namespaces)
kubectl top pods --all-namespaces

# View pod usage in specific namespace
kubectl top pods -n NAMESPACE

# View container-level metrics within a pod
kubectl top pod POD_NAME --containers -n NAMESPACE

# Compare actual usage vs requests/limits
kubectl get pods -o custom-columns=\
NAME:.metadata.name,\
CPU_REQ:.spec.containers[*].resources.requests.cpu,\
CPU_LIM:.spec.containers[*].resources.limits.cpu,\
MEM_REQ:.spec.containers[*].resources.requests.memory,\
MEM_LIM:.spec.containers[*].resources.limits.memory
```

#### Find Over-Provisioned Pods

```bash
#!/bin/bash
# find-overprovisioned-pods.sh
# Compare requested resources vs actual usage

kubectl top pods --all-namespaces --no-headers | while read line; do
  NS=$(echo $line | awk '{print $1}')
  POD=$(echo $line | awk '{print $2}')
  CPU_USED=$(echo $line | awk '{print $3}' | tr -d 'm')
  MEM_USED=$(echo $line | awk '{print $4}' | tr -d 'Mi')
  
  # Get requested resources
  REQ=$(kubectl get pod $POD -n $NS -o jsonpath='{.spec.containers[0].resources.requests}' 2>/dev/null)
  
  if [ ! -z "$REQ" ]; then
    CPU_REQ=$(kubectl get pod $POD -n $NS -o jsonpath='{.spec.containers[0].resources.requests.cpu}' 2>/dev/null | tr -d 'm')
    
    if [ ! -z "$CPU_REQ" ] && [ "$CPU_REQ" -gt 0 ]; then
      UTILIZATION=$((CPU_USED * 100 / CPU_REQ))
      if [ "$UTILIZATION" -lt 20 ]; then
        echo "$NS/$POD: Using ${CPU_USED}m of ${CPU_REQ}m requested (${UTILIZATION}%)"
      fi
    fi
  fi
done
```

---

### 3. Detecting Pods Without Resource Limits

```bash
# Find pods without CPU limits
kubectl get pods --all-namespaces -o json | jq -r '
  .items[] | 
  select(.spec.containers[].resources.limits.cpu == null) |
  "\(.metadata.namespace)/\(.metadata.name)"'

# Find pods without memory limits
kubectl get pods --all-namespaces -o json | jq -r '
  .items[] | 
  select(.spec.containers[].resources.limits.memory == null) |
  "\(.metadata.namespace)/\(.metadata.name)"'

# Find pods without any resource requests
kubectl get pods --all-namespaces -o json | jq -r '
  .items[] | 
  select(.spec.containers[].resources.requests == null) |
  "\(.metadata.namespace)/\(.metadata.name)"'
```

---

### 4. Detecting Service Mesh / Inter-Service Communication Issues

#### With Istio Service Mesh

```bash
# Check if Istio is installed
kubectl get pods -n istio-system

# Get Istio proxy configuration for a pod
istioctl proxy-config cluster POD_NAME -n NAMESPACE

# View service dependencies
istioctl proxy-config endpoints POD_NAME -n NAMESPACE

# Get Envoy metrics from a sidecar
kubectl exec POD_NAME -c istio-proxy -n NAMESPACE -- \
  curl -s localhost:15000/stats | grep -E "(upstream_rq|downstream_rq)"

# Check inter-service request counts
kubectl exec POD_NAME -c istio-proxy -n NAMESPACE -- \
  curl -s localhost:15000/stats | grep "cluster.*upstream_rq_completed"
```

#### Get Istio Metrics via Prometheus

```bash
# Port-forward to Prometheus
kubectl port-forward svc/prometheus -n istio-system 9090:9090 &

# Query inter-service traffic (using curl to Prometheus API)
curl -s 'http://localhost:9090/api/v1/query' \
  --data-urlencode 'query=sum(rate(istio_requests_total[5m])) by (source_app, destination_app)' | jq '.data.result'
```

---

### 5. Detecting HPA Configuration Issues

```bash
# List all Horizontal Pod Autoscalers
kubectl get hpa --all-namespaces

# Check HPA status and scaling behavior
kubectl describe hpa HPA_NAME -n NAMESPACE

# Find HPAs that haven't scaled (current = min for extended period)
kubectl get hpa --all-namespaces -o json | jq -r '
  .items[] | 
  select(.status.currentReplicas == .spec.minReplicas) |
  "\(.metadata.namespace)/\(.metadata.name): stuck at minReplicas=\(.spec.minReplicas)"'
```

---

### 6. Kubernetes Resource Quotas and Limits

```bash
# View resource quotas by namespace
kubectl get resourcequotas --all-namespaces

# View limit ranges
kubectl get limitranges --all-namespaces

# Check actual usage vs quotas
kubectl describe resourcequota -n NAMESPACE
```

---

## Docker / Docker Compose Detection Commands

### Single VM / Docker Host

---

### 1. Real-Time Container Resource Usage

```bash
# View all container stats (live updating)
docker stats

# Snapshot (non-streaming)
docker stats --no-stream

# Custom format
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}"

# JSON output for scripting
docker stats --no-stream --format '{{json .}}'
```

---

### 2. Detect Idle Containers

```bash
#!/bin/bash
# find-idle-containers.sh - Find containers with < 1% CPU usage

echo "Idle Containers (CPU < 1%):"
echo "==========================="

docker stats --no-stream --format '{{.Name}}\t{{.CPUPerc}}' | while read line; do
  NAME=$(echo "$line" | cut -f1)
  CPU=$(echo "$line" | cut -f2 | tr -d '%')
  
  # Handle decimal values
  CPU_INT=$(echo "$CPU" | cut -d'.' -f1)
  
  if [ "${CPU_INT:-0}" -lt 1 ]; then
    MEM=$(docker stats --no-stream --format '{{.MemPerc}}' "$NAME" 2>/dev/null)
    echo "$NAME: CPU ${CPU}%, Memory ${MEM}"
  fi
done
```

---

### 3. Container Memory Analysis

```bash
# Get detailed memory stats from cgroups
docker inspect --format '{{.State.Pid}}' CONTAINER_NAME | xargs -I {} cat /proc/{}/status | grep -E "VmRSS|VmSize"

# Check memory limits vs usage
docker stats --no-stream --format "{{.Name}}: {{.MemUsage}} ({{.MemPerc}} of limit)"

# Find containers near memory limit (> 80%)
docker stats --no-stream --format '{{.Name}}\t{{.MemPerc}}' | while read line; do
  NAME=$(echo "$line" | cut -f1)
  MEM_PCT=$(echo "$line" | cut -f2 | tr -d '%')
  MEM_INT=$(echo "$MEM_PCT" | cut -d'.' -f1)
  
  if [ "${MEM_INT:-0}" -gt 80 ]; then
    echo "WARNING: $NAME is at ${MEM_PCT}% memory"
  fi
done
```

---

### 4. Docker Compose Service Analysis

```bash
# List services and their status
docker compose ps

# View logs for potential errors
docker compose logs --tail=100

# Check resource usage per service
docker compose top

# Get stats for compose project containers
docker stats $(docker compose ps -q) --no-stream
```

---

### 5. Network I/O Analysis

```bash
# View network stats for all containers
docker stats --no-stream --format "{{.Name}}: Net I/O {{.NetIO}}"

# Check for containers with high network usage (potential chatty services)
docker stats --no-stream --format '{{.Name}}\t{{.NetIO}}' | while read line; do
  NAME=$(echo "$line" | cut -f1)
  NET=$(echo "$line" | cut -f2)
  # Parse network I/O (format: "1.5MB / 500kB")
  echo "$NAME: $NET"
done
```

---

### 6. Detecting Containers Without Resource Limits

```bash
# Find containers without memory limits
docker ps -q | xargs docker inspect --format '{{.Name}}: Memory={{.HostConfig.Memory}} MemorySwap={{.HostConfig.MemorySwap}}' | grep "Memory=0"

# Find containers without CPU limits
docker ps -q | xargs docker inspect --format '{{.Name}}: CPUShares={{.HostConfig.CpuShares}} CPUQuota={{.HostConfig.CpuQuota}}' | grep -E "CPUShares=0|CPUQuota=0"
```

---

### 7. cAdvisor for Historical Metrics

```bash
# Run cAdvisor for detailed container monitoring
docker run \
  --volume=/:/rootfs:ro \
  --volume=/var/run:/var/run:ro \
  --volume=/sys:/sys:ro \
  --volume=/var/lib/docker/:/var/lib/docker:ro \
  --volume=/dev/disk/:/dev/disk:ro \
  --publish=8080:8080 \
  --detach=true \
  --name=cadvisor \
  gcr.io/cadvisor/cadvisor:latest

# Access metrics at http://localhost:8080/metrics
curl -s http://localhost:8080/metrics | grep -E "container_cpu|container_memory"
```

---

## Prometheus / PromQL Queries

### Prerequisites

```bash
# Using promql-cli
go install github.com/nalbury/promql-cli@latest

# Or use curl with Prometheus API
PROMETHEUS_URL="http://localhost:9090"
```

---

### 1. Detecting Underutilized Services

```bash
# CPU usage by pod (< 10% is potentially idle)
curl -s "$PROMETHEUS_URL/api/v1/query" \
  --data-urlencode 'query=
    sum(rate(container_cpu_usage_seconds_total{container!=""}[5m])) by (pod)
    / 
    sum(kube_pod_container_resource_requests{resource="cpu"}) by (pod)
    < 0.1
  ' | jq '.data.result'

# Memory usage vs requests (< 20% is over-provisioned)
curl -s "$PROMETHEUS_URL/api/v1/query" \
  --data-urlencode 'query=
    sum(container_memory_working_set_bytes{container!=""}) by (pod)
    /
    sum(kube_pod_container_resource_requests{resource="memory"}) by (pod)
    < 0.2
  ' | jq '.data.result'
```

---

### 2. Inter-Service Communication Metrics (Istio)

```bash
# Request rate between services
curl -s "$PROMETHEUS_URL/api/v1/query" \
  --data-urlencode 'query=
    sum(rate(istio_requests_total[5m])) by (source_app, destination_app)
  ' | jq '.data.result'

# Find chatty services (> 1000 RPS between any pair)
curl -s "$PROMETHEUS_URL/api/v1/query" \
  --data-urlencode 'query=
    sum(rate(istio_requests_total[5m])) by (source_app, destination_app) > 1000
  ' | jq '.data.result'

# P99 latency between services
curl -s "$PROMETHEUS_URL/api/v1/query" \
  --data-urlencode 'query=
    histogram_quantile(0.99, 
      sum(rate(istio_request_duration_milliseconds_bucket[5m])) 
      by (source_app, destination_app, le)
    )
  ' | jq '.data.result'

# Error rate between services
curl -s "$PROMETHEUS_URL/api/v1/query" \
  --data-urlencode 'query=
    sum(rate(istio_requests_total{response_code=~"5.*"}[5m])) by (source_app, destination_app)
    /
    sum(rate(istio_requests_total[5m])) by (source_app, destination_app)
  ' | jq '.data.result'
```

---

### 3. Node Resource Utilization

```bash
# Node CPU utilization percentage
curl -s "$PROMETHEUS_URL/api/v1/query" \
  --data-urlencode 'query=
    100 - (avg by (instance) (irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)
  ' | jq '.data.result'

# Nodes with < 20% CPU utilization (underutilized)
curl -s "$PROMETHEUS_URL/api/v1/query" \
  --data-urlencode 'query=
    100 - (avg by (instance) (irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) < 20
  ' | jq '.data.result'

# Memory utilization percentage
curl -s "$PROMETHEUS_URL/api/v1/query" \
  --data-urlencode 'query=
    (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100
  ' | jq '.data.result'
```

---

### 4. HTTP Request Metrics (Generic)

```bash
# Request rate by service
curl -s "$PROMETHEUS_URL/api/v1/query" \
  --data-urlencode 'query=
    sum(rate(http_requests_total[5m])) by (service)
  ' | jq '.data.result'

# P95 latency
curl -s "$PROMETHEUS_URL/api/v1/query" \
  --data-urlencode 'query=
    histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, service))
  ' | jq '.data.result'

# Error rate
curl -s "$PROMETHEUS_URL/api/v1/query" \
  --data-urlencode 'query=
    sum(rate(http_requests_total{status=~"5.."}[5m])) by (service)
    /
    sum(rate(http_requests_total[5m])) by (service)
  ' | jq '.data.result'
```

---

### 5. Useful PromQL Alerts for Energy Anti-Patterns

```yaml
# prometheus-rules.yaml - Example alerting rules

groups:
- name: energy-efficiency
  rules:
  
  # Alert on idle nodes
  - alert: NodeUnderutilized
    expr: 100 - (avg by (instance) (irate(node_cpu_seconds_total{mode="idle"}[1h])) * 100) < 15
    for: 24h
    labels:
      severity: warning
    annotations:
      summary: "Node {{ $labels.instance }} underutilized (< 15% CPU for 24h)"
  
  # Alert on over-provisioned pods
  - alert: PodOverProvisioned
    expr: |
      sum(rate(container_cpu_usage_seconds_total{container!=""}[1h])) by (pod, namespace)
      /
      sum(kube_pod_container_resource_requests{resource="cpu"}) by (pod, namespace)
      < 0.1
    for: 24h
    labels:
      severity: info
    annotations:
      summary: "Pod {{ $labels.namespace }}/{{ $labels.pod }} using < 10% of requested CPU"
  
  # Alert on chatty service pairs
  - alert: ChattyMicroservices
    expr: sum(rate(istio_requests_total[5m])) by (source_app, destination_app) > 5000
    for: 1h
    labels:
      severity: warning
    annotations:
      summary: "High traffic between {{ $labels.source_app }} and {{ $labels.destination_app }}"
```

---

## Database Query Analysis

### PostgreSQL

#### Enable Slow Query Logging

```bash
# Connect to PostgreSQL and enable logging
psql -U postgres -c "ALTER SYSTEM SET log_min_duration_statement = 1000;"  # Log queries > 1 second
psql -U postgres -c "ALTER SYSTEM SET log_statement = 'all';"  # Or 'ddl', 'mod', 'none'
psql -U postgres -c "SELECT pg_reload_conf();"

# View current settings
psql -U postgres -c "SHOW log_min_duration_statement;"
```

#### Find Repeated Queries (N+1 Pattern Detection)

```sql
-- Using pg_stat_statements extension
-- Enable it first:
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Find most frequently called queries (potential N+1)
SELECT 
  calls,
  mean_exec_time::numeric(10,2) as avg_ms,
  total_exec_time::numeric(10,2) as total_ms,
  query
FROM pg_stat_statements
ORDER BY calls DESC
LIMIT 20;

-- Find queries with high total time
SELECT 
  calls,
  mean_exec_time::numeric(10,2) as avg_ms,
  total_exec_time::numeric(10,2) as total_ms,
  query
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;

-- Identify repeated similar queries (N+1 pattern)
SELECT 
  left(query, 100) as query_pattern,
  count(*) as similar_queries,
  sum(calls) as total_calls
FROM pg_stat_statements
GROUP BY left(query, 100)
HAVING count(*) > 1
ORDER BY sum(calls) DESC
LIMIT 20;
```

#### Find Queries Without Index Usage

```sql
-- Find sequential scans on large tables
SELECT 
  schemaname,
  relname as table_name,
  seq_scan,
  seq_tup_read,
  idx_scan,
  n_live_tup as row_count
FROM pg_stat_user_tables
WHERE seq_scan > 0 
  AND n_live_tup > 10000
ORDER BY seq_tup_read DESC
LIMIT 20;

-- Find missing indexes
SELECT 
  schemaname || '.' || relname as table,
  seq_scan - idx_scan as too_many_seq_scans,
  pg_size_pretty(pg_relation_size(relid)) as size
FROM pg_stat_user_tables
WHERE seq_scan - idx_scan > 0
ORDER BY seq_scan - idx_scan DESC
LIMIT 20;
```

---

### MySQL

#### Enable Slow Query Log

```bash
# Via MySQL CLI
mysql -u root -p -e "SET GLOBAL slow_query_log = 'ON';"
mysql -u root -p -e "SET GLOBAL long_query_time = 1;"  # Log queries > 1 second
mysql -u root -p -e "SET GLOBAL log_queries_not_using_indexes = 'ON';"

# Check current settings
mysql -u root -p -e "SHOW VARIABLES LIKE 'slow_query%';"
mysql -u root -p -e "SHOW VARIABLES LIKE 'long_query_time';"
```

#### Analyze Slow Query Log

```bash
# Use mysqldumpslow to analyze slow query log
mysqldumpslow -s t /var/log/mysql/mysql-slow.log | head -20

# Sort by count (find repeated queries)
mysqldumpslow -s c /var/log/mysql/mysql-slow.log | head -20

# Using pt-query-digest (Percona Toolkit)
pt-query-digest /var/log/mysql/mysql-slow.log

# Find top 10 queries by total time
pt-query-digest --limit=10 /var/log/mysql/mysql-slow.log
```

#### Find Queries Without Index (MySQL)

```sql
-- Check queries not using indexes
SHOW GLOBAL STATUS LIKE 'Select_full_join';
SHOW GLOBAL STATUS LIKE 'Select_scan';

-- Find tables without indexes
SELECT 
  table_schema,
  table_name,
  table_rows
FROM information_schema.tables
WHERE table_schema NOT IN ('information_schema', 'mysql', 'performance_schema')
  AND table_name NOT IN (
    SELECT DISTINCT table_name 
    FROM information_schema.statistics 
    WHERE table_schema = tables.table_schema
  )
ORDER BY table_rows DESC;
```

---

### Redis Cache Analysis

```bash
# Check cache hit ratio
redis-cli INFO stats | grep -E "keyspace_hits|keyspace_misses"

# Calculate hit ratio
redis-cli INFO stats | awk -F: '
  /keyspace_hits/ {hits=$2}
  /keyspace_misses/ {misses=$2}
  END {
    total = hits + misses
    if (total > 0) {
      ratio = hits / total * 100
      printf "Cache Hit Ratio: %.2f%%\n", ratio
      printf "Hits: %d, Misses: %d\n", hits, misses
    }
  }
'

# Check memory usage
redis-cli INFO memory | grep -E "used_memory_human|maxmemory_human"

# Find large keys (potential cache inefficiency)
redis-cli --bigkeys

# Check key expiration stats
redis-cli INFO stats | grep -E "expired_keys|evicted_keys"
```

---

## Infrastructure-as-Code Static Analysis

### Terraform Analysis

```bash
# Find resources without auto-scaling
grep -rL "autoscaling" --include="*.tf" ./infra | xargs grep -l "aws_instance\|aws_ecs_service"

# Find hardcoded instance counts
grep -rEn 'desired_count\s*=\s*[0-9]+|count\s*=\s*[0-9]+' --include="*.tf" ./infra

# Find resources without tags (harder to identify idle resources)
grep -rL "tags" --include="*.tf" ./infra | xargs grep -l "resource \"aws_"

# Find instances without monitoring enabled
grep -rE 'resource\s+"aws_instance"' -A 50 --include="*.tf" ./infra | grep -v "monitoring\s*=\s*true"
```

### Kubernetes Manifest Analysis

```bash
# Find deployments without resource limits
grep -rL "resources:" --include="*.yaml" --include="*.yml" ./k8s | xargs grep -l "kind: Deployment"

# Find deployments without HPA
for DEPLOY in $(grep -rl "kind: Deployment" --include="*.yaml" ./k8s); do
  NAME=$(grep -A5 "kind: Deployment" "$DEPLOY" | grep "name:" | head -1 | awk '{print $2}')
  if ! grep -rq "scaleTargetRef.*$NAME" --include="*.yaml" ./k8s; then
    echo "No HPA for: $DEPLOY ($NAME)"
  fi
done

# Find pods without liveness/readiness probes
grep -rL "livenessProbe\|readinessProbe" --include="*.yaml" ./k8s | xargs grep -l "kind: Deployment\|kind: Pod"

# Find services without resource requests
grep -rE "kind:\s*Deployment" -A 100 --include="*.yaml" ./k8s | grep -B 50 -A 50 "containers:" | grep -L "requests:"
```

### Docker Compose Analysis

```bash
# Find services without memory limits
grep -rL "mem_limit\|memory:" --include="docker-compose*.yml" --include="docker-compose*.yaml" ./

# Find services without CPU limits
grep -rL "cpus:\|cpu_shares:" --include="docker-compose*.yml" ./

# Find services without health checks
grep -rL "healthcheck:" --include="docker-compose*.yml" ./

# Find services without restart policies
grep -rL "restart:" --include="docker-compose*.yml" ./
```

---

## Automated Detection Scripts

### Comprehensive AWS Audit Script

```bash
#!/bin/bash
# aws-energy-audit.sh - Comprehensive AWS energy efficiency audit

echo "=========================================="
echo "AWS Energy Efficiency Audit"
echo "Date: $(date)"
echo "=========================================="

echo ""
echo "=== 1. Idle EC2 Instances ==="
./find-idle-ec2.sh 2>/dev/null || echo "Script not found"

echo ""
echo "=== 2. Stopped Instances with Attached Resources ==="
aws ec2 describe-instances \
  --filters "Name=instance-state-name,Values=stopped" \
  --query 'Reservations[*].Instances[*].[InstanceId,InstanceType]' \
  --output table

echo ""
echo "=== 3. Unattached EBS Volumes ==="
aws ec2 describe-volumes \
  --filters "Name=status,Values=available" \
  --query 'Volumes[*].[VolumeId,Size,VolumeType]' \
  --output table

echo ""
echo "=== 4. Unassociated Elastic IPs ==="
aws ec2 describe-addresses \
  --query 'Addresses[?AssociationId==`null`].[PublicIp,AllocationId]' \
  --output table

echo ""
echo "=== 5. Unused Lambda Functions ==="
./find-unused-lambdas.sh 2>/dev/null || echo "Script not found"

echo ""
echo "=== 6. Compute Optimizer Recommendations ==="
aws compute-optimizer get-ec2-instance-recommendations \
  --query 'instanceRecommendations[?finding==`OVER_PROVISIONED`].[instanceArn,currentInstanceType,recommendationOptions[0].instanceType]' \
  --output table 2>/dev/null || echo "Compute Optimizer not enabled"

echo ""
echo "=========================================="
echo "Audit Complete"
echo "=========================================="
```

### Comprehensive Kubernetes Audit Script

```bash
#!/bin/bash
# k8s-energy-audit.sh - Comprehensive Kubernetes energy efficiency audit

echo "=========================================="
echo "Kubernetes Energy Efficiency Audit"
echo "Date: $(date)"
echo "=========================================="

echo ""
echo "=== 1. Node Utilization ==="
kubectl top nodes 2>/dev/null || echo "Metrics server not available"

echo ""
echo "=== 2. Underutilized Nodes (< 20% CPU) ==="
kubectl top nodes --no-headers 2>/dev/null | while read line; do
  NAME=$(echo $line | awk '{print $1}')
  CPU_PCT=$(echo $line | awk '{print $3}' | tr -d '%')
  if [ "${CPU_PCT:-100}" -lt 20 ]; then
    echo "$NAME: ${CPU_PCT}%"
  fi
done

echo ""
echo "=== 3. Pods Without Resource Limits ==="
kubectl get pods --all-namespaces -o json 2>/dev/null | jq -r '
  .items[] | 
  select(.spec.containers[].resources.limits == null) |
  "\(.metadata.namespace)/\(.metadata.name)"' | head -20

echo ""
echo "=== 4. Top CPU-Consuming Pods ==="
kubectl top pods --all-namespaces --sort-by=cpu 2>/dev/null | head -15

echo ""
echo "=== 5. Top Memory-Consuming Pods ==="
kubectl top pods --all-namespaces --sort-by=memory 2>/dev/null | head -15

echo ""
echo "=== 6. HPA Status ==="
kubectl get hpa --all-namespaces 2>/dev/null

echo ""
echo "=========================================="
echo "Audit Complete"
echo "=========================================="
```

### Docker Host Audit Script

```bash
#!/bin/bash
# docker-energy-audit.sh - Docker host energy efficiency audit

echo "=========================================="
echo "Docker Energy Efficiency Audit"
echo "Date: $(date)"
echo "=========================================="

echo ""
echo "=== 1. Container Resource Usage ==="
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemPerc}}\t{{.NetIO}}"

echo ""
echo "=== 2. Idle Containers (< 1% CPU) ==="
docker stats --no-stream --format '{{.Name}}\t{{.CPUPerc}}' | while read line; do
  NAME=$(echo "$line" | cut -f1)
  CPU=$(echo "$line" | cut -f2 | tr -d '%' | cut -d'.' -f1)
  if [ "${CPU:-100}" -lt 1 ]; then
    echo "$NAME: idle"
  fi
done

echo ""
echo "=== 3. Containers Without Memory Limits ==="
docker ps -q | xargs docker inspect --format '{{.Name}}: Memory={{.HostConfig.Memory}}' 2>/dev/null | grep "Memory=0"

echo ""
echo "=== 4. Containers Without CPU Limits ==="
docker ps -q | xargs docker inspect --format '{{.Name}}: CPUQuota={{.HostConfig.CpuQuota}}' 2>/dev/null | grep "CPUQuota=0"

echo ""
echo "=== 5. Stopped Containers ==="
docker ps -a --filter "status=exited" --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"

echo ""
echo "=== 6. Dangling Images ==="
docker images -f "dangling=true" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"

echo ""
echo "=========================================="
echo "Audit Complete"
echo "=========================================="
```

---

## Sources

### AWS Documentation & Tools

1. **AWS CLI CloudWatch Reference**
   - https://docs.aws.amazon.com/cli/latest/reference/cloudwatch/

2. **AWS Compute Optimizer Documentation**
   - https://docs.aws.amazon.com/compute-optimizer/

3. **CloudWatch Lambda Insights**
   - https://docs.aws.amazon.com/lambda/latest/dg/monitoring-insights.html

4. **ProsperOps - Identifying Idle Resources**
   - https://www.prosperops.com/blog/identify-idle-underutilized-cloud-resources/

### Google Cloud Documentation

5. **GCloud Compute Commands**
   - https://docs.cloud.google.com/compute/docs/gcloud-compute

6. **Idle VM Recommendations**
   - https://docs.cloud.google.com/compute/docs/instances/viewing-and-applying-idle-vm-recommendations

7. **GCloud Recommender**
   - https://cloud.google.com/recommender/docs

### Kubernetes & Prometheus

8. **kubectl top Documentation**
   - https://kubernetes.io/docs/reference/kubectl/generated/kubectl_top/

9. **Prometheus PromQL**
   - https://prometheus.io/docs/prometheus/latest/querying/basics/

10. **Kubernetes Metrics Server**
    - https://github.com/kubernetes-sigs/metrics-server

11. **Four Golden Signals - Sysdig**
    - https://www.sysdig.com/blog/golden-signals-kubernetes

### Istio & Service Mesh

12. **Istio Observability**
    - https://istio.io/latest/docs/concepts/observability/

13. **Istio Standard Metrics**
    - https://istio.io/latest/docs/reference/config/metrics/

### Docker

14. **Docker Stats Documentation**
    - https://docs.docker.com/reference/cli/docker/container/stats/

15. **Docker Runtime Metrics**
    - https://docs.docker.com/engine/containers/runmetrics/

16. **cAdvisor**
    - https://github.com/google/cadvisor

### Database Performance

17. **PostgreSQL pg_stat_statements**
    - https://www.postgresql.org/docs/current/pgstatstatements.html

18. **MySQL Slow Query Log**
    - https://dev.mysql.com/doc/refman/8.0/en/slow-query-log.html

19. **Percona pt-query-digest**
    - https://docs.percona.com/percona-toolkit/pt-query-digest.html

### Additional Tools

20. **promql-cli**
    - https://github.com/nalbury/promql-cli

21. **AWS Cost Optimization Tool (Open Source)**
    - https://github.com/charles-bucher/AWS-Cost-Optimization-Tool-

---

## Document Information

- **Created**: February 2026
- **Purpose**: CLI-based detection of architectural energy anti-patterns
- **Companion to**: `code-level-energy-antipatterns-detection.md`

---

*"Architectural inefficiencies multiply across your entire infrastructure. A single over-provisioned service running 24/7 wastes more energy than thousands of unoptimized code paths. Use these commands to find the big wins first."*
