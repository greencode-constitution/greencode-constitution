# Terraform Energy Antipatterns

Agent skill for detecting and fixing energy-wasting antipatterns in Terraform/IaC-managed infrastructure.

---

## 1. No Auto-Scaling Configured

Resources provisioned at fixed sizes, wasting energy during low-demand periods.

### Detect

```bash
# Find compute resources without autoscaling
grep -rL "autoscaling\|aws_autoscaling\|google_compute_autoscaler" --include="*.tf" . \
  | xargs grep -l "aws_instance\|aws_ecs_service\|google_compute_instance"

# Find hardcoded instance counts
grep -rEn 'desired_count\s*=\s*[0-9]+|count\s*=\s*[0-9]+' --include="*.tf" .

# Find fixed-size ASGs (min == max == desired)
grep -rEn 'min_size|max_size|desired_capacity' --include="*.tf" .
```

### Fix

- **Add auto-scaling** to compute resources:
  ```hcl
  resource "aws_autoscaling_group" "app" {
    min_size         = 1
    max_size         = 10
    desired_capacity = 2

    tag {
      key                 = "Name"
      value               = "app"
      propagate_at_launch = true
    }
  }

  resource "aws_autoscaling_policy" "target_tracking" {
    autoscaling_group_name = aws_autoscaling_group.app.name
    policy_type            = "TargetTrackingScaling"

    target_tracking_configuration {
      predefined_metric_specification {
        predefined_metric_type = "ASGAverageCPUUtilization"
      }
      target_value = 60.0
    }
  }
  ```
- **Use `min_size` < `desired_capacity` < `max_size`** — never set them equal.
- **Use scale-to-zero** where possible (Lambda, Fargate, Cloud Run).

---

## 2. Over-Provisioned Instance Types

Hardcoded large instance types that far exceed workload needs.

### Detect

```bash
# Find instance type declarations
grep -rEn 'instance_type\s*=\s*"[^"]*"' --include="*.tf" .
grep -rEn 'machine_type\s*=\s*"[^"]*"' --include="*.tf" .

# Look for large/expensive types
grep -rEn 'instance_type\s*=\s*"(m5\.(x|2x|4x|8x)|c5\.(2x|4x|9x|18x)|r5\.)' --include="*.tf" .
```

### Fix

- **Use variables** for instance types so environments can differ:
  ```hcl
  variable "instance_type" {
    default = "t4g.small"  # Graviton-based, energy efficient
  }
  ```
- **Use Graviton/Arm** types (`t4g`, `m7g`, `c7g` on AWS; `t2a` on GCP).
- **Use burstable types** (`t3`, `t4g`) for workloads with variable CPU needs.
- **Reference Compute Optimizer** output to pick the right size.

---

## 3. Resources Without Tags/Labels

Untagged resources are impossible to audit for waste, making idle resources invisible.

### Detect

```bash
# Find AWS resources without tags
grep -rL "tags" --include="*.tf" . | xargs grep -l 'resource "aws_'

# Find GCP resources without labels
grep -rL "labels" --include="*.tf" . | xargs grep -l 'resource "google_'
```

### Fix

- **Add mandatory tags** to all resources:
  ```hcl
  resource "aws_instance" "app" {
    # ...
    tags = {
      Name        = "app-server"
      Environment = var.environment
      Team        = var.team
      CostCenter  = var.cost_center
    }
  }
  ```
- **Enforce tagging with policy as code** (Sentinel, OPA, tflint):
  ```hcl
  # tflint rule
  rule "aws_resource_missing_tags" {
    enabled = true
    tags    = ["Environment", "Team", "CostCenter"]
  }
  ```

---

## 4. No Monitoring Enabled

Resources deployed without CloudWatch/monitoring, so waste goes undetected.

### Detect

```bash
# EC2 without detailed monitoring
grep -rE 'resource\s+"aws_instance"' -A 30 --include="*.tf" . | grep -L "monitoring\s*=\s*true"

# No CloudWatch alarms defined
grep -rL "aws_cloudwatch_metric_alarm\|google_monitoring_alert_policy" --include="*.tf" .
```

### Fix

- **Enable detailed monitoring** on EC2:
  ```hcl
  resource "aws_instance" "app" {
    monitoring = true
    # ...
  }
  ```
- **Add CloudWatch alarms** for idle detection:
  ```hcl
  resource "aws_cloudwatch_metric_alarm" "low_cpu" {
    alarm_name          = "low-cpu-utilization"
    comparison_operator = "LessThanThreshold"
    evaluation_periods  = 4
    metric_name         = "CPUUtilization"
    namespace           = "AWS/EC2"
    period              = 21600  # 6 hours
    statistic           = "Average"
    threshold           = 10
    alarm_actions       = [aws_sns_topic.alerts.arn]
    dimensions = {
      InstanceId = aws_instance.app.id
    }
  }
  ```

---

## 5. Always-On Non-Production Environments

Dev/staging environments running 24/7 via Terraform but only used during business hours.

### Detect

```bash
# Find environment-specific workspaces or variables
grep -rEn 'environment\s*=\s*"(dev|staging|test)"' --include="*.tf" --include="*.tfvars" .

# Check if any scheduling/lifecycle exists
grep -rL "aws_autoscaling_schedule\|google_compute_resource_policy\|schedule" --include="*.tf" .
```

### Fix

- **Add scheduled scaling** to reduce to 0 outside hours:
  ```hcl
  resource "aws_autoscaling_schedule" "night_off" {
    scheduled_action_name  = "night-shutdown"
    autoscaling_group_name = aws_autoscaling_group.dev.name
    min_size               = 0
    max_size               = 0
    desired_capacity       = 0
    recurrence             = "0 20 * * MON-FRI"  # 8 PM
  }

  resource "aws_autoscaling_schedule" "morning_on" {
    scheduled_action_name  = "morning-startup"
    autoscaling_group_name = aws_autoscaling_group.dev.name
    min_size               = 1
    max_size               = 3
    desired_capacity       = 1
    recurrence             = "0 8 * * MON-FRI"  # 8 AM
  }
  ```
- **Use Instance Scheduler** (AWS) or **Instance Schedules** (GCP) for non-ASG resources.
- **Use Terraform workspaces** to easily destroy/recreate ephemeral environments.

---

## 6. Kubernetes Manifests Without Resource Limits

IaC-managed K8s deployments missing resource requests/limits.

### Detect

```bash
# Deployments without resource blocks
grep -rL "resources:" --include="*.yaml" --include="*.yml" . | xargs grep -l "kind: Deployment"

# Deployments without HPA
for DEPLOY in $(grep -rl "kind: Deployment" --include="*.yaml" .); do
  NAME=$(grep -A5 "kind: Deployment" "$DEPLOY" | grep "name:" | head -1 | awk '{print $2}')
  if ! grep -rq "scaleTargetRef.*$NAME" --include="*.yaml" .; then
    echo "No HPA: $DEPLOY ($NAME)"
  fi
done

# Missing probes
grep -rL "livenessProbe\|readinessProbe" --include="*.yaml" --include="*.yml" . \
  | xargs grep -l "kind: Deployment\|kind: Pod"
```

### Fix

- **Add resource requests/limits** to every container spec.
- **Add HPA** for all user-facing deployments.
- **Add liveness/readiness probes** so failed pods get restarted instead of idling.
- See the [kubernetes.md](kubernetes.md) skill for detailed K8s solutions.

---

## 7. EBS/Disk Over-Provisioning

Volumes provisioned with high IOPS or large sizes far exceeding needs.

### Detect

```bash
# Find volume definitions
grep -rEn 'volume_size\s*=\s*[0-9]+|size\s*=\s*[0-9]+' --include="*.tf" .
grep -rEn 'volume_type\s*=\s*"io[12]"' --include="*.tf" .
grep -rEn 'iops\s*=\s*[0-9]+' --include="*.tf" .
```

### Fix

- **Use `gp3` instead of `io1`/`io2`** for most workloads — 20% cheaper with configurable IOPS.
- **Right-size volume sizes** based on actual usage.
- **Use lifecycle policies** to transition infrequently accessed data to cheaper storage.
- **Check Compute Optimizer** EBS recommendations before provisioning.
