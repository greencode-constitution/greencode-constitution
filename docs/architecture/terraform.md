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

---

## 8. Missing Storage Lifecycle Policies

S3 buckets and GCS buckets provisioned via Terraform without lifecycle rules keep data forever, wasting storage energy on objects nobody accesses.

### Detect

```bash
# S3 buckets without lifecycle rules
grep -rl 'resource "aws_s3_bucket"' --include="*.tf" . | while read FILE; do
  BUCKET=$(grep -A5 'resource "aws_s3_bucket"' "$FILE" | grep -oP '"\K[^"]+' | head -1)
  if ! grep -q "aws_s3_bucket_lifecycle_configuration" "$FILE" && \
     ! grep -rq "bucket.*=.*${BUCKET}.*lifecycle" --include="*.tf" .; then
    echo "NO LIFECYCLE: $FILE ($BUCKET)"
  fi
done

# GCS buckets without lifecycle rules
grep -rn 'resource "google_storage_bucket"' --include="*.tf" . | while read LINE; do
  FILE=$(echo "$LINE" | cut -d: -f1)
  if ! grep -A30 'resource "google_storage_bucket"' "$FILE" | grep -q 'lifecycle_rule'; then
    echo "NO LIFECYCLE: $FILE"
  fi
done
```

### Fix

- **Add lifecycle configuration** for AWS S3:
  ```hcl
  resource "aws_s3_bucket_lifecycle_configuration" "default" {
    bucket = aws_s3_bucket.data.id

    rule {
      id     = "archive-and-expire"
      status = "Enabled"

      transition {
        days          = 90
        storage_class = "STANDARD_IA"
      }
      transition {
        days          = 180
        storage_class = "GLACIER"
      }
      expiration {
        days = 365
      }
    }
  }
  ```
- **Add lifecycle rules** for GCS:
  ```hcl
  resource "google_storage_bucket" "data" {
    name     = "my-data-bucket"
    location = "US"

    lifecycle_rule {
      condition { age = 90 }
      action { type = "SetStorageClass" storage_class = "NEARLINE" }
    }
    lifecycle_rule {
      condition { age = 365 }
      action { type = "Delete" }
    }
  }
  ```

---

## 9. Missing CDN for Static Content

IaC that deploys web-facing applications without a CDN in front of static assets forces every request to traverse the full network path to origin servers, wasting energy.

### Detect

```bash
# S3 website buckets without CloudFront
grep -rl 'resource "aws_s3_bucket_website_configuration"' --include="*.tf" . | while read FILE; do
  DIR=$(dirname "$FILE")
  if ! grep -rq 'resource "aws_cloudfront_distribution"' --include="*.tf" "$DIR"; then
    echo "NO CDN: $FILE — S3 website without CloudFront"
  fi
done

# Public ALBs without CloudFront
grep -rl 'resource "aws_lb"' --include="*.tf" . | while read FILE; do
  if grep -q 'internal.*false\|scheme.*internet-facing' "$FILE"; then
    DIR=$(dirname "$FILE")
    if ! grep -rq 'aws_cloudfront_distribution' --include="*.tf" "$DIR"; then
      echo "NO CDN: $FILE — public ALB without CloudFront"
    fi
  fi
done

# GCP backend services without CDN
grep -rn 'resource "google_compute_backend_service"' --include="*.tf" . | while read LINE; do
  FILE=$(echo "$LINE" | cut -d: -f1)
  if ! grep -A20 'resource "google_compute_backend_service"' "$FILE" | grep -q 'enable_cdn.*true'; then
    echo "NO CDN: $FILE"
  fi
done
```

### Fix

- **Add CloudFront** for AWS:
  ```hcl
  resource "aws_cloudfront_distribution" "cdn" {
    origin {
      domain_name = aws_s3_bucket.static.bucket_regional_domain_name
      origin_id   = "s3-static"
    }

    enabled             = true
    default_root_object = "index.html"

    default_cache_behavior {
      allowed_methods  = ["GET", "HEAD"]
      cached_methods   = ["GET", "HEAD"]
      target_origin_id = "s3-static"
      compress         = true

      forwarded_values {
        query_string = false
        cookies { forward = "none" }
      }

      viewer_protocol_policy = "redirect-to-https"
    }

    restrictions {
      geo_restriction { restriction_type = "none" }
    }

    viewer_certificate {
      cloudfront_default_certificate = true
    }
  }
  ```
- **Enable CDN** on GCP backend services:
  ```hcl
  resource "google_compute_backend_service" "default" {
    name       = "web-backend"
    enable_cdn = true

    cdn_policy {
      cache_mode                   = "CACHE_ALL_STATIC"
      default_ttl                  = 3600
      signed_url_cache_max_age_sec = 7200
    }
  }
  ```

---

## 10. Missing WAF/DDoS Protection

Public-facing infrastructure without WAF or DDoS protection allows malicious traffic to consume compute resources, wasting energy on nonsensical requests.

### Detect

```bash
# Public ALBs without WAF association
grep -rl 'resource "aws_lb"' --include="*.tf" . | while read FILE; do
  DIR=$(dirname "$FILE")
  if ! grep -rq 'aws_wafv2_web_acl_association' --include="*.tf" "$DIR"; then
    echo "NO WAF: $FILE"
  fi
done

# Missing WAF resources entirely
grep -rL 'aws_wafv2\|google_compute_security_policy\|azurerm_web_application_firewall' --include="*.tf" . \
  | xargs grep -l 'aws_lb\|aws_cloudfront\|google_compute_backend_service'

# Missing DDoS protection
grep -rL 'aws_shield\|azurerm_network_ddos_protection' --include="*.tf" .
```

### Fix

- **Add WAF** for AWS:
  ```hcl
  resource "aws_wafv2_web_acl" "main" {
    name  = "main-waf"
    scope = "REGIONAL"

    default_action { allow {} }

    rule {
      name     = "rate-limit"
      priority = 1
      action { block {} }

      statement {
        rate_based_statement {
          limit              = 2000
          aggregate_key_type = "IP"
        }
      }

      visibility_config {
        sampled_requests_enabled   = true
        cloudwatch_metrics_enabled = true
        metric_name                = "rate-limit"
      }
    }

    visibility_config {
      sampled_requests_enabled   = true
      cloudwatch_metrics_enabled = true
      metric_name                = "main-waf"
    }
  }

  resource "aws_wafv2_web_acl_association" "alb" {
    resource_arn = aws_lb.main.arn
    web_acl_arn  = aws_wafv2_web_acl.main.arn
  }
  ```
- **Add Cloud Armor** for GCP:
  ```hcl
  resource "google_compute_security_policy" "default" {
    name = "default-policy"

    rule {
      action   = "deny(403)"
      priority = 1000
      match {
        expr { expression = "evaluatePreconfiguredExpr('xss-v33-stable')" }
      }
    }

    rule {
      action   = "allow"
      priority = 2147483647
      match {
        versioned_expr = "SRC_IPS_V1"
        config { src_ip_ranges = ["*"] }
      }
    }
  }
  ```

---

## 11. Over-Engineered Availability for Non-Critical Workloads

Multi-AZ deployments, hot standby replicas, and multi-region failover for internal tools or low-impact services waste energy on redundant infrastructure.

### Detect

```bash
# RDS multi-AZ for non-production
grep -rEn 'multi_az\s*=\s*true' --include="*.tf" .
grep -rEn 'multi_az' -B20 --include="*.tf" . | grep -iE 'dev|staging|test|internal'

# Read replicas for low-traffic databases
grep -rn 'aws_db_instance.*replica\|replicate_source_db' --include="*.tf" .

# Global tables / cross-region replication for non-critical
grep -rn 'aws_dynamodb_global_table\|google_sql_database_instance.*replica' --include="*.tf" .

# Multiple replicas for internal-only services
grep -rEn 'replicas\s*=\s*[3-9]' --include="*.yaml" --include="*.yml" . \
  | xargs grep -l 'internal\|backoffice\|admin'
```

### Fix

- **Disable multi-AZ** for dev/staging/internal databases:
  ```hcl
  resource "aws_db_instance" "internal" {
    multi_az = false  # only enable for production customer-facing DBs
    # ...
  }
  ```
- **Remove read replicas** from low-traffic services.
- **Reduce replica count** for internal services to 1-2 instead of 3+.
- **Document SLO requirements** per service and match infrastructure accordingly.
