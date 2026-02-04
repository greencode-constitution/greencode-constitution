# AWS Energy Antipatterns

Agent skill for detecting and fixing energy-wasting antipatterns in AWS infrastructure.

---

## 1. Idle EC2 Instances

Instances running with <10% CPU and <5 MB network I/O over 7+ days.

### Detect

```bash
# List running instances
aws ec2 describe-instances \
  --filters "Name=instance-state-name,Values=running" \
  --query 'Reservations[*].Instances[*].[InstanceId,InstanceType,LaunchTime,Tags[?Key==`Name`].Value|[0]]' \
  --output table

# Check CPU for a specific instance (7-day avg)
aws cloudwatch get-metric-statistics \
  --namespace AWS/EC2 --metric-name CPUUtilization \
  --dimensions Name=InstanceId,Value=INSTANCE_ID \
  --start-time $(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%SZ) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --period 86400 --statistics Average Maximum --output table

# Batch: find all instances with avg CPU < 10%
for ID in $(aws ec2 describe-instances --filters "Name=instance-state-name,Values=running" \
  --query 'Reservations[*].Instances[*].InstanceId' --output text); do
  AVG=$(aws cloudwatch get-metric-statistics --namespace AWS/EC2 --metric-name CPUUtilization \
    --dimensions Name=InstanceId,Value=$ID \
    --start-time $(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%SZ) \
    --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
    --period 604800 --statistics Average \
    --query 'Datapoints[0].Average' --output text 2>/dev/null)
  if [ "$(echo "$AVG < 10" | bc -l 2>/dev/null)" = "1" ]; then
    echo "IDLE: $ID (avg CPU: $AVG%)"
  fi
done
```

### Fix

- **Terminate** truly unused instances.
- **Rightsize** to a smaller instance type: `aws ec2 modify-instance-attribute --instance-id ID --instance-type '{"Value":"t3.small"}'` (requires stop first).
- **Switch to Graviton** (e.g. `t4g.*`, `m7g.*`) — up to 60% less energy for equivalent performance.
- **Use Compute Optimizer** for automated recommendations:
  ```bash
  aws compute-optimizer get-ec2-instance-recommendations \
    --query 'instanceRecommendations[*].[instanceArn,finding,currentInstanceType,recommendationOptions[0].instanceType]' \
    --output table
  ```
- **Enable auto-scaling** instead of static provisioning.

---

## 2. Stopped Instances with Attached Resources

Stopped EC2s still incur costs for EBS volumes, Elastic IPs, and snapshots.

### Detect

```bash
# Stopped instances
aws ec2 describe-instances \
  --filters "Name=instance-state-name,Values=stopped" \
  --query 'Reservations[*].Instances[*].[InstanceId,InstanceType,LaunchTime]' --output table

# Unattached EBS volumes
aws ec2 describe-volumes \
  --filters "Name=status,Values=available" \
  --query 'Volumes[*].[VolumeId,Size,VolumeType,CreateTime]' --output table

# Unassociated Elastic IPs
aws ec2 describe-addresses \
  --query 'Addresses[?AssociationId==`null`].[PublicIp,AllocationId]' --output table
```

### Fix

- **Terminate** stopped instances that have been idle >7 days.
- **Delete** unattached EBS volumes: `aws ec2 delete-volume --volume-id VOL_ID`
- **Release** unused Elastic IPs: `aws ec2 release-address --allocation-id ALLOC_ID`
- **Snapshot** important volumes before deleting for archival.

---

## 3. Idle Load Balancers

ALBs/NLBs with zero request count or no healthy targets.

### Detect

```bash
# List ALBs
aws elbv2 describe-load-balancers \
  --query 'LoadBalancers[*].[LoadBalancerName,LoadBalancerArn,State.Code]' --output table

# Check request count (7 days)
aws cloudwatch get-metric-statistics \
  --namespace AWS/ApplicationELB --metric-name RequestCount \
  --dimensions Name=LoadBalancer,Value=app/ALB_NAME/LB_ID \
  --start-time $(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%SZ) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --period 604800 --statistics Sum --output table

# Check target health
for ALB_ARN in $(aws elbv2 describe-load-balancers --query 'LoadBalancers[*].LoadBalancerArn' --output text); do
  for TG_ARN in $(aws elbv2 describe-target-groups --load-balancer-arn $ALB_ARN \
    --query 'TargetGroups[*].TargetGroupArn' --output text); do
    aws elbv2 describe-target-health --target-group-arn $TG_ARN \
      --query 'TargetHealthDescriptions[*].[Target.Id,TargetHealth.State]' --output table
  done
done
```

### Fix

- **Delete** ALBs with zero traffic: `aws elbv2 delete-load-balancer --load-balancer-arn ARN`
- **Consolidate** multiple low-traffic ALBs behind a single one using path-based routing.
- **Remove** orphaned target groups.

---

## 4. Idle RDS Instances

Database instances with zero connections or <5% CPU over extended periods.

### Detect

```bash
# List RDS instances
aws rds describe-db-instances \
  --query 'DBInstances[*].[DBInstanceIdentifier,DBInstanceClass,DBInstanceStatus,Engine]' --output table

# Check connections (7 days)
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS --metric-name DatabaseConnections \
  --dimensions Name=DBInstanceIdentifier,Value=DB_ID \
  --start-time $(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%SZ) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --period 86400 --statistics Average Maximum --output table

# Check CPU
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS --metric-name CPUUtilization \
  --dimensions Name=DBInstanceIdentifier,Value=DB_ID \
  --start-time $(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%SZ) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --period 86400 --statistics Average --output table
```

### Fix

- **Delete** instances with zero connections for 30+ days (snapshot first).
- **Rightsize** to a smaller instance class.
- **Switch to Aurora Serverless** for variable workloads — scales to zero when idle.
- **Stop** dev/staging RDS instances during off-hours: `aws rds stop-db-instance --db-instance-identifier DB_ID`

---

## 5. Lambda Cold Starts & Idle Functions

Functions with zero invocations or excessive cold start overhead.

### Detect

```bash
# List functions
aws lambda list-functions \
  --query 'Functions[*].[FunctionName,Runtime,MemorySize,LastModified]' --output table

# Check invocations (30 days)
for FUNC in $(aws lambda list-functions --query 'Functions[*].FunctionName' --output text); do
  COUNT=$(aws cloudwatch get-metric-statistics --namespace AWS/Lambda --metric-name Invocations \
    --dimensions Name=FunctionName,Value=$FUNC \
    --start-time $(date -u -d '30 days ago' +%Y-%m-%dT%H:%M:%SZ) \
    --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
    --period 2592000 --statistics Sum \
    --query 'Datapoints[0].Sum' --output text 2>/dev/null)
  if [ "$COUNT" == "None" ] || [ "$COUNT" == "0.0" ]; then
    echo "UNUSED: $FUNC"
  fi
done

# Analyze cold starts via CloudWatch Logs Insights
aws logs start-query \
  --log-group-name "/aws/lambda/FUNC_NAME" \
  --start-time $(date -u -d '7 days ago' +%s) --end-time $(date -u +%s) \
  --query-string 'filter @type="REPORT" | stats count(*) as invocations, count(@initDuration) as coldStarts, avg(@initDuration) as avgColdStartMs by bin(1h)'
```

### Fix

- **Delete** unused functions.
- **Rightsize memory** using Compute Optimizer:
  ```bash
  aws compute-optimizer get-lambda-function-recommendations \
    --query 'lambdaFunctionRecommendations[*].[functionArn,finding,currentMemorySize,memorySizeRecommendationOptions[0].memorySize]' \
    --output table
  ```
- **Use provisioned concurrency** for latency-critical functions to reduce cold starts.
- **Switch to Graviton** runtime (`arm64`) for ~34% better price/performance.
- **Reduce package size** — strip unused dependencies, use layers.

---

## 6. Idle NAT Gateways

NAT Gateways with zero bytes transferred.

### Detect

```bash
# List NAT Gateways
aws ec2 describe-nat-gateways \
  --query 'NatGateways[*].[NatGatewayId,State,SubnetId,CreateTime]' --output table

# Check bytes transferred (14 days)
aws cloudwatch get-metric-statistics \
  --namespace AWS/NATGateway --metric-name BytesOutToDestination \
  --dimensions Name=NatGatewayId,Value=NAT_GW_ID \
  --start-time $(date -u -d '14 days ago' +%Y-%m-%dT%H:%M:%SZ) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --period 86400 --statistics Sum --output table
```

### Fix

- **Delete** idle NAT Gateways: `aws ec2 delete-nat-gateway --nat-gateway-id NAT_GW_ID`
- **Use VPC endpoints** for AWS service traffic instead of routing through NAT.
- **Consolidate** multiple NAT Gateways if traffic allows.

---

## 7. Over-Provisioned Infrastructure (General)

Resources running far below capacity due to conservative sizing.

### Detect

```bash
# Enable Compute Optimizer
aws compute-optimizer update-enrollment-status --status Active

# EC2 recommendations
aws compute-optimizer get-ec2-instance-recommendations \
  --query 'instanceRecommendations[?finding==`OVER_PROVISIONED`].[instanceArn,currentInstanceType,recommendationOptions[0].instanceType]' \
  --output table

# EBS recommendations
aws compute-optimizer get-ebs-volume-recommendations \
  --query 'volumeRecommendations[?finding==`NotOptimized`].[volumeArn,currentConfiguration.volumeType,volumeRecommendationOptions[0].configuration.volumeType]' \
  --output table
```

### Fix

- **Apply rightsizing recommendations** from Compute Optimizer.
- **Switch EBS types** (e.g. `gp2` → `gp3` for better price/performance).
- **Use auto-scaling groups** with target tracking policies instead of static fleets.
- **Adopt Graviton instances** across workloads for lower energy per unit of compute.
- **Schedule non-production** environments to shut down outside business hours.
