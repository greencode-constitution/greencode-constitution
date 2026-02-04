# Cloud Infrastructure Energy Patterns: Detection & Optimization Guide

> Cloud-level patterns that reduce energy consumption and carbon emissions, with grep/regex patterns to find optimization opportunities in your codebase and infrastructure-as-code.
>
> Source: [Green Software Foundation — Cloud Catalog](https://patterns.greensoftware.foundation/catalog/cloud/)

---

## Table of Contents

1. [Overview](#overview)
2. [Caching & Data Locality](#1-caching--data-locality)
3. [Compression](#2-compression)
4. [Containerization & Serverless](#3-containerization--serverless)
5. [Storage Optimization](#4-storage-optimization)
6. [Encryption & Security Overhead](#5-encryption--security-overhead)
7. [CPU & Hardware Efficiency](#6-cpu--hardware-efficiency)
8. [Stateless & Microservice Design](#7-stateless--microservice-design)
9. [Scaling & Autoscaling](#8-scaling--autoscaling)
10. [Network Optimization](#9-network-optimization)
11. [Async & Queue-Based Processing](#10-async--queue-based-processing)
12. [Resilience Patterns](#11-resilience-patterns)
13. [Environment & Resource Lifecycle](#12-environment--resource-lifecycle)
14. [Security as Sustainability](#13-security-as-sustainability)
15. [Time-Shifting & Carbon-Aware Scheduling](#14-time-shifting--carbon-aware-scheduling)
16. [Language & Compilation](#15-language--compilation)
17. [Customer-Side Impact](#16-customer-side-impact)

---

## Overview

Each pattern in this document includes:
- **Summary**: What the technique is and why it reduces energy/carbon
- **Grep Patterns**: Regex patterns an agent can use to find related code, config, or IaC
- **Potential Solutions**: Concrete steps to apply the optimization

### Using the Grep Patterns

```bash
# Search IaC files (Terraform, CloudFormation, Kubernetes)
grep -rEn "PATTERN" --include="*.tf" --include="*.yaml" --include="*.yml" --include="*.json" .

# Search application code
grep -rEn "PATTERN" --include="*.py" --include="*.java" --include="*.go" --include="*.ts" ./src

# With context (3 lines before/after)
grep -rEn -B3 -A3 "PATTERN" .
```

---

## 1. Caching & Data Locality

### 1.1 Cache Static Data

**Summary**: Store static assets (images, fonts, CSS, JS bundles) in local or in-memory caches instead of fetching them repeatedly over the network. Reduces energy by shortening network packet travel distance and lowering the number of computing devices traversed.

**Grep Patterns** (find missing cache headers or repeated fetches):
```
# No cache-control headers in responses
Cache-Control:\s*no-cache|no-store
# HTTP fetches inside loops or repeated calls
fetch\(|requests\.get\(|http\.Get\(|axios\.\w+\(
# Static assets served without CDN/cache config
\.png|\.jpg|\.jpeg|\.gif|\.svg|\.woff|\.ttf|\.css|\.js
# Terraform/IaC: missing CDN or caching layer
resource\s+"aws_cloudfront|google_compute_backend_bucket|azurerm_cdn
```

**Potential Solutions**:
- Add `Cache-Control` and `ETag` headers for static assets
- Deploy a CDN (CloudFront, Cloud CDN, Azure CDN) in front of static content
- Use in-memory caches (Redis, Memcached) for frequently-read data
- Implement service worker caching for web apps

### 1.2 Choose Region Closest to Users

**Summary**: Deploy applications in cloud regions geographically nearest to your users. Shorter network paths require less energy for transmission and traverse fewer network devices, reducing embodied carbon.

**Grep Patterns** (find region configuration in IaC):
```
# Terraform provider region settings
region\s*=\s*"
# Kubernetes node selectors or topology constraints
topology\.kubernetes\.io/region
failure-domain\.beta\.kubernetes\.io/region
# CloudFormation region references
AWS::Region
# Hardcoded region strings far from user base (review manually)
us-east-1|us-west-2|eu-west-1|ap-southeast-1
```

**Potential Solutions**:
- Analyze user traffic geography (e.g., via analytics or CDN logs) and match deployment region
- Use multi-region deployments with latency-based routing for globally distributed users
- Review region selection in Terraform `provider` blocks or Kubernetes cluster configs
- Consider edge computing for latency-sensitive workloads

---

## 2. Compression

### 2.1 Compress Stored Data

**Summary**: Use compression for stored data to reduce storage capacity requirements and bandwidth. Weigh compression CPU cost against storage savings — for large datasets the net benefit is almost always positive.

**Grep Patterns** (find uncompressed storage or missing compression config):
```
# S3 buckets or GCS without compression/lifecycle
resource\s+"aws_s3_bucket"|resource\s+"google_storage_bucket"
# Large file writes without compression
open\(.+,\s*['"]w['"]\)|\.write\(|\.writelines\(
# Database bulk inserts without compression
COPY\s+\w+\s+FROM|LOAD\s+DATA|bulk_write|insertMany
# Missing gzip/brotli in storage config
content_encoding|ContentEncoding|compress
```

**Potential Solutions**:
- Enable server-side compression on object storage (S3, GCS, Azure Blob)
- Use columnar formats with built-in compression (Parquet, ORC) for analytical data
- Compress log files and backups (gzip, zstd, lz4)
- Enable transparent compression on databases where supported (ZFS, PostgreSQL TOAST)

### 2.2 Compress Transmitted Data

**Summary**: Compress data before sending it across the network. Reduces network energy consumption, though compression/decompression has its own CPU cost.

**Grep Patterns** (find uncompressed API responses or missing compression middleware):
```
# Web servers/frameworks without compression middleware
app\.use\(|middleware|MIDDLEWARE
# Missing gzip/brotli in nginx/Apache config
gzip\s+on|mod_deflate|brotli
# API responses returning large payloads
Content-Type:\s*application/json
# HTTP responses without Accept-Encoding handling
Accept-Encoding|Content-Encoding
```

**Potential Solutions**:
- Enable gzip/brotli compression in web servers (nginx: `gzip on;`)
- Add compression middleware in application frameworks (Express `compression()`, Django `GZipMiddleware`)
- Use binary serialization formats (Protobuf, MessagePack) instead of JSON/XML for internal APIs
- Compress WebSocket frames for real-time applications

---

## 3. Containerization & Serverless

### 3.1 Containerize Your Workloads

**Summary**: Containers package applications with minimal dependencies, using less CPU and RAM than full VMs. Efficient bin packing reduces total compute resource allocation. Pair with microservices for maximum benefit.

**Grep Patterns** (find VM-based deployments that could be containerized):
```
# VM-based IaC resources
resource\s+"aws_instance"|resource\s+"google_compute_instance"|resource\s+"azurerm_virtual_machine"
# Vagrantfile (local VM provisioning)
Vagrant\.configure
# Large base images in Dockerfiles
FROM\s+(ubuntu|debian|centos|fedora|node):\s*latest
# Missing multi-stage builds
FROM.*\nRUN.*install
```

**Potential Solutions**:
- Migrate VM workloads to containers using Docker/Kubernetes
- Use minimal base images (Alpine, distroless, scratch)
- Implement multi-stage Docker builds to reduce image size
- Adopt container orchestration (Kubernetes, ECS) for efficient scheduling

### 3.2 Use Serverless Cloud Services

**Summary**: Serverless platforms (AWS Lambda, Cloud Functions, Azure Functions) share infrastructure across applications and only consume resources when invoked. Eliminates idle resource waste but may introduce cold-start latency.

**Grep Patterns** (find always-on services that could be serverless):
```
# Long-running servers for infrequent tasks
app\.listen\(|http\.createServer|serve_forever|ListenAndServe
# Cron-based tasks on dedicated servers
crontab|schedule\.|@scheduled|CronJob
# Low-traffic API endpoints on full servers
flask\.Flask|express\(\)|gin\.Default|fiber\.New
# IaC: dedicated VMs for lightweight tasks
instance_type\s*=\s*"t[23]\.(micro|small|nano)"
```

**Potential Solutions**:
- Migrate event-driven or low-traffic workloads to serverless functions
- Use serverless databases (DynamoDB, Cloud Firestore) for variable workloads
- Implement serverless API gateways for infrequent-use endpoints
- Evaluate cold-start tolerance before migrating latency-sensitive paths

---

## 4. Storage Optimization

### 4.1 Delete Unused Storage Resources

**Summary**: Remove orphaned storage volumes, snapshots, and disks that are no longer attached to active workloads. Directly lowers embodied carbon from unnecessary hardware.

**Grep Patterns** (find potentially orphaned storage in IaC):
```
# EBS volumes or persistent disks without attachments
resource\s+"aws_ebs_volume"|resource\s+"google_compute_disk"|resource\s+"azurerm_managed_disk"
# Snapshots without lifecycle policies
resource\s+"aws_ebs_snapshot"|resource\s+"google_compute_snapshot"
# Detached volume references
available|unattached|Detached
```

**Potential Solutions**:
- Audit cloud storage with `aws ec2 describe-volumes --filters Name=status,Values=available`
- Set up automated alerts for unattached volumes (AWS Config, GCP Recommender)
- Implement tagging policies to track volume ownership
- Use cloud cost tools (Infracost, AWS Cost Explorer) to identify idle resources

### 4.2 Optimize Storage Utilization

**Summary**: Consolidate underutilized storage resources. A single storage unit at high utilization is more energy-efficient than multiple units at low utilization.

**Grep Patterns**:
```
# Over-provisioned storage in IaC
size\s*=\s*[0-9]{4,}|storage_gb\s*=|disk_size_gb
# Multiple small PVCs in Kubernetes
kind:\s*PersistentVolumeClaim
# Hardcoded large volume sizes
volumeSize|diskSizeGb|allocated_storage
```

**Potential Solutions**:
- Right-size storage volumes based on actual usage metrics
- Use auto-expanding storage (e.g., AWS EBS autoscaling, GCP automatic disk resize)
- Consolidate multiple small volumes into shared storage where appropriate
- Implement storage tiering (hot/cold/archive) based on access patterns

### 4.3 Set Storage Retention Policies

**Summary**: Automate deletion of unused storage resources based on retention rules instead of keeping data indefinitely. Reduces embodied carbon by requiring fewer physical storage devices.

**Grep Patterns** (find storage without lifecycle/retention policies):
```
# S3 buckets without lifecycle rules
resource\s+"aws_s3_bucket"(?!.*lifecycle)
# GCS without lifecycle
resource\s+"google_storage_bucket"(?!.*lifecycle_rule)
# Kubernetes PVCs without reclaim policy
persistentVolumeReclaimPolicy|reclaimPolicy
# Log storage without rotation
log_group|LogGroup|logging\.handlers
```

**Potential Solutions**:
- Configure S3 lifecycle policies to transition objects to cheaper tiers and eventually delete
- Set Cloud Storage lifecycle rules with age-based deletion
- Implement log rotation and retention limits (e.g., CloudWatch log retention)
- Use database TTL features (DynamoDB TTL, MongoDB TTL indexes) for ephemeral data

---

## 5. Encryption & Security Overhead

### 5.1 Encrypt Only What Is Necessary

**Summary**: Encrypt only sensitive data rather than applying encryption universally. Encryption is CPU-intensive and increases storage requirements. Classify data by sensitivity and encrypt accordingly.

**Grep Patterns** (find blanket encryption patterns):
```
# Encrypting everything at rest
server_side_encryption|encryption_configuration|kms_key_id
# Encrypting all columns/fields
@Encrypted|encrypted=True|ENCRYPT\(
# Full-disk encryption on non-sensitive workloads
encrypted\s*=\s*true
```

**Potential Solutions**:
- Classify data into sensitivity tiers; only encrypt PII, credentials, and regulated data
- Use column-level or field-level encryption instead of full-database encryption where possible
- Choose efficient encryption algorithms (AES-256-GCM over RSA for bulk data)
- Segregate sensitive and non-sensitive data into separate storage with different encryption policies

### 5.2 Terminate TLS at Border Gateway

**Summary**: End TLS encryption at the network border gateway rather than maintaining it through to every backend service. Reduces redundant encrypt/decrypt CPU cycles for internal traffic.

**Grep Patterns** (find end-to-end TLS in internal services):
```
# TLS config in every microservice
ssl_context|tls\.Config|SSLContext|https://localhost
# Mutual TLS between internal services
mtls|mutual_tls|client_certificate|clientAuth
# Certificate mounts in every pod
secretName.*tls|ssl-cert|tls\.crt
# Internal HTTPS calls between services
https://.*\.svc\.cluster\.local|https://.*internal
```

**Potential Solutions**:
- Offload TLS termination to ingress controllers (nginx-ingress, Traefik, AWS ALB)
- Use plaintext HTTP for internal service-to-service communication within trusted networks
- Implement TLS termination at API gateway or load balancer level
- Evaluate compliance requirements before removing internal encryption

---

## 6. CPU & Hardware Efficiency

### 6.1 Evaluate Alternative CPU Architectures

**Summary**: Assess ARM-based or other energy-efficient processors (e.g., AWS Graviton, Ampere Altra) instead of defaulting to x86-64. Different architectures offer different energy-to-performance ratios.

**Grep Patterns** (find x86-locked configurations):
```
# Instance types locked to x86
instance_type\s*=\s*"(m5|c5|r5|m6i|c6i|t3)"
machine_type\s*=\s*"(n2|e2|c2)-"
# Docker images only built for amd64
--platform\s*linux/amd64|TARGETARCH|amd64
# Architecture-specific binaries
GOARCH=amd64|x86_64|--target=x86
```

**Potential Solutions**:
- Test workloads on ARM instances (AWS Graviton `m6g/c6g/r6g`, Azure `Dpsv5`, GCP `t2a`)
- Build multi-architecture Docker images (`docker buildx --platform linux/amd64,linux/arm64`)
- Use CI/CD to cross-compile and test on both architectures
- Benchmark energy consumption per request on different architectures

### 6.2 Use Cloud Native Processor VMs

**Summary**: Deploy on VMs with energy-efficient cloud-native processors (ARM-based chips like Ampere Altra). These consume less electricity and have lower embodied carbon than traditional x86 processors. Particularly suitable for scale-out, cloud-native workloads.

**Grep Patterns** (find non-optimized VM SKUs):
```
# Generic or older instance families
instance_type\s*=\s*"(m5|m4|c5|c4|t3|t2)\."
machine_type\s*=\s*"(n1|n2)-standard"
vm_size\s*=\s*"Standard_(D|E|F)[0-9]"
# Missing ARM/Graviton references
graviton|ampere|arm64|aarch64
```

**Potential Solutions**:
- Migrate to Graviton-based instances on AWS (`m7g`, `c7g`, `r7g`)
- Use Ampere Altra VMs on Azure (`Dpsv5`, `Epsv5`)
- Use Tau T2A instances on GCP
- Verify application and dependency compatibility with ARM before migrating

### 6.3 Optimize Average CPU Utilization

**Summary**: Bring average CPU utilization closer to an optimal level rather than running many underutilized instances. There is no universal target — fast-scaling systems can sustain higher averages; slower-scaling systems need more headroom.

**Grep Patterns** (find over-provisioned compute):
```
# Very large instance types (potentially over-provisioned)
instance_type\s*=\s*".+\.(2?x?large|4xlarge|8xlarge|metal)"
# Low CPU autoscaling thresholds
target_cpu_utilization_percentage:\s*[1-3][0-9]\b
cpu_target\s*=\s*(0\.[1-3])
# Fixed replica counts (no autoscaling)
replicas:\s*[0-9]+
```

**Potential Solutions**:
- Implement CPU-based autoscaling with appropriate thresholds (typically 50-70%)
- Right-size instances using cloud provider recommendations (AWS Compute Optimizer, GCP Recommender)
- Use burstable instances (T-series) for variable workloads
- Monitor and alert on sustained low CPU utilization

### 6.4 Optimize Peak CPU Utilization

**Summary**: Reduce CPU spikes by understanding what drives peaks and flattening them through caching, queuing, and data reduction. Large gaps between average and peak utilization force idle standby resources.

**Grep Patterns** (find spike-prone patterns):
```
# Synchronous heavy processing without queuing
\.forEach\(|\.map\(.*=>.*await|for.*range.*goroutine
# Missing caching for expensive operations
@Cacheable|lru_cache|functools\.cache|memoize
# Large batch operations without throttling
batch_size|chunk_size|BATCH_SIZE|LIMIT\s+[0-9]{5,}
```

**Potential Solutions**:
- Add caching layers (Redis, in-memory) for repeated expensive computations
- Queue non-urgent work to spread processing over time
- Implement request throttling and rate limiting
- Use read replicas to distribute database query load

### 6.5 Match VM Utilization Requirements

**Summary**: Right-size VMs so that allocated resources match actual usage. One VM at high utilization is more energy-efficient than two at low utilization. Use autoscaling for variable workloads instead of permanently oversizing.

**Grep Patterns**:
```
# Oversized static VM allocations
instance_type\s*=\s*".*xlarge"
machine_type\s*=\s*".*-standard-(8|16|32|64|96)"
# Fixed (non-autoscaled) VM counts
count\s*=\s*[0-9]+
desired_capacity\s*=
# Resources requests much larger than limits in Kubernetes
resources:\s*\n\s*requests:
```

**Potential Solutions**:
- Audit CPU/memory usage and downsize instances to match real demand
- Use cloud rightsizing tools (AWS Compute Optimizer, GCP Recommender, Azure Advisor)
- Implement horizontal autoscaling instead of vertical over-provisioning
- Periodically review and adjust instance types based on utilization data

### 6.6 Match Utilization with Pre-configured Servers

**Summary**: Select pre-configured server sizes that align with actual workload demands instead of defaulting to large instances. Consolidate workloads onto appropriately-sized machines for better energy proportionality.

**Grep Patterns**:
```
# Default or generic sizing
instance_type\s*=\s*".*\.large"
machine_type\s*=\s*".*-standard-[0-9]+"
# Manual capacity planning without monitoring
min_size|max_size|desired_capacity
```

**Potential Solutions**:
- Profile application resource usage under realistic load before choosing instance size
- Start with smaller instances and scale up based on observed metrics
- Use cloud provider sizing calculators and recommendation engines
- Implement auto-scaling to handle demand spikes rather than permanent over-provisioning

---

## 7. Stateless & Microservice Design

### 7.1 Implement Stateless Design

**Summary**: Remove in-memory and on-disk state from services; externalize state to databases or caching services. Stateless services can run on smaller VMs and scale more efficiently, reducing both energy and embodied carbon.

**Grep Patterns** (find stateful patterns in services):
```
# In-memory session stores
session\[|req\.session|HttpSession|flask\.session
# Local file-based state
tempfile|NamedTemporaryFile|os\.path\.join.*state|\.dat
# Sticky sessions in load balancers
sticky|stickiness|session_affinity|JSESSIONID
# In-process caching that prevents horizontal scaling
@lru_cache|ConcurrentHashMap|sync\.Map|global\s+\w+\s*=\s*\{\}
```

**Potential Solutions**:
- Move session state to external stores (Redis, DynamoDB, Memcached)
- Follow the 12-factor app methodology for stateless process design
- Use object storage (S3, GCS) instead of local filesystem for uploads/artifacts
- Replace in-process caches with distributed caches

### 7.2 Scale Logical Components Independently

**Summary**: Break monoliths into microservices that scale independently based on individual demand. Only scale the bottleneck component rather than the entire application. Balance against microservice communication overhead.

**Grep Patterns** (find monolithic scaling):
```
# Single deployment with many responsibilities
replicas:\s*[0-9]+.*# (entire app|monolith|all services)
# Monolithic Dockerfiles with many COPY/RUN steps
COPY\s+\.\s+\.|RUN\s+.*&&.*&&.*&&
# Single process handling multiple concerns
@app\.route.*\n.*@app\.route|router\.get.*\n.*router\.get
# Tightly coupled services sharing databases
DATABASE_URL.*shared|connection_string.*common
```

**Potential Solutions**:
- Decompose monoliths into microservices along domain boundaries
- Use Kubernetes Horizontal Pod Autoscaler (HPA) per service
- Consider gRPC instead of HTTP for inter-service communication to reduce overhead
- Avoid over-decomposition — keep microservices at a meaningful granularity

---

## 8. Scaling & Autoscaling

### 8.1 Scale Down Kubernetes Applications When Not in Use

**Summary**: Scale pods to zero during predictable low-traffic periods (nights, weekends). Works at pod level for production and node level for dev/test. No code changes needed — operates at the platform level.

**Grep Patterns** (find always-on Kubernetes workloads):
```
# Fixed replica counts without time-based scaling
replicas:\s*[1-9][0-9]*
# Missing KEDA or CronJob-based scaler
kind:\s*ScaledObject|kind:\s*CronJob
# Dev/test namespaces running 24/7
namespace:\s*(dev|staging|test|qa|uat)
# Deployments without HPA
kind:\s*Deployment(?!.*HorizontalPodAutoscaler)
```

**Potential Solutions**:
- Use KEDA `Cron` scaler to set replicas to 0 outside business hours
- Implement namespace-level shutdown schedules for dev/test environments
- Use tools like `kube-downscaler` for automated time-based scaling
- Configure cluster autoscaler to remove empty nodes

### 8.2 Scale Down Applications When Not in Use

**Summary**: Automatically shut down or reduce applications and underlying infrastructure during inactivity using cloud-native scheduling. Applications consume power through background processes even when idle.

**Grep Patterns** (find always-running non-production resources):
```
# Dev/staging VMs without auto-stop
resource\s+"aws_instance".*tags.*Environment.*(dev|staging|test)
# Always-on scheduled tasks
schedule\s*=\s*"rate\(1\s*(minute|hour)|cron\(.*\*.*\*.*\*"
# Missing auto-shutdown configuration
auto_stop|auto_shutdown|scheduleExpression
```

**Potential Solutions**:
- Configure auto-stop schedules for dev/test VMs (AWS Instance Scheduler, Azure auto-shutdown)
- Use serverless for workloads that don't need 24/7 availability
- Implement shutdown scripts triggered by inactivity monitoring
- Set up cost anomaly alerts to catch forgotten resources

### 8.3 Scale Infrastructure with User Load

**Summary**: Dynamically adjust computing resources based on actual demand. Shut down or consolidate excess capacity during low-activity windows. Reduces both operational electricity and embodied carbon.

**Grep Patterns** (find static infrastructure):
```
# Fixed instance counts without autoscaling groups
count\s*=\s*[0-9]+
desired_capacity\s*=\s*[0-9]+
# Missing autoscaling configuration
aws_autoscaling_group|google_compute_autoscaler|azurerm_monitor_autoscale_setting
# Hardcoded min/max with no scaling policy
min_size\s*=.*max_size\s*=.*\bmin_size\s*==\s*max_size
```

**Potential Solutions**:
- Implement autoscaling groups with CPU/memory-based scaling policies
- Use predictive scaling (AWS Predictive Scaling) for workloads with known patterns
- Set appropriate min/max boundaries to allow meaningful scaling range
- Combine horizontal (more instances) and vertical (bigger instances) scaling

### 8.4 Scale Kubernetes Workloads Based on Relevant Demand Metrics

**Summary**: Configure Kubernetes autoscaling using custom metrics that reflect actual demand (HTTP request rate, queue length) rather than just CPU/RAM. Enables scaling to zero when there is no demand.

**Grep Patterns** (find basic HPA configs that only use CPU/memory):
```
# HPA using only CPU metric
type:\s*Resource\s*\n\s*resource:\s*\n\s*name:\s*cpu
# Missing KEDA or custom metrics adapter
kind:\s*ScaledObject|external\.metrics|custom\.metrics
# Default CPU threshold autoscaling
targetCPUUtilizationPercentage
# Missing scale-to-zero capability
minReplicas:\s*[1-9]
```

**Potential Solutions**:
- Deploy KEDA for event-driven autoscaling with custom metrics
- Configure HPA with custom metrics (Prometheus adapter, Datadog metrics)
- Set `minReplicas: 0` with KEDA to enable scale-to-zero
- Use queue-length or request-rate metrics for more accurate scaling decisions

### 8.5 Match Service Level Objectives to Business Needs

**Summary**: Align availability guarantees with actual business requirements instead of over-engineering for unnecessary uptime. Hot standby systems and excessive redundancy consume significant energy for little real-world benefit if not genuinely needed.

**Grep Patterns** (find over-engineered availability):
```
# Multi-AZ or multi-region for non-critical workloads
multi_az\s*=\s*true|cross_region_replica|global_table
# Multiple replicas for low-traffic services
replicas:\s*[3-9][0-9]*
# Hot standby databases for non-critical apps
standby|read_replica|failover
# SLA/SLO configuration
availability.*99\.99|uptime.*five.nines
```

**Potential Solutions**:
- Review SLOs against actual business impact of downtime
- Reduce replica counts for internal or non-customer-facing services
- Use cold standby instead of hot standby for non-critical databases
- Document and justify availability requirements for each service

---

## 9. Network Optimization

### 9.1 Reduce Network Traversal Between VMs

**Summary**: Place VMs in the same region or availability zone to minimize physical network distance. Shorter paths use less energy. Balance against availability requirements that may need cross-AZ distribution.

**Grep Patterns** (find cross-zone/region communication):
```
# VMs spread across zones without placement groups
availability_zone|placement_group|node_affinity
# Cross-region service calls
region.*!=|cross.region|inter.region
# Network traffic between different subnets
subnet_id.*!=|different.*subnet
# Missing placement or affinity rules in Kubernetes
podAffinity|podAntiAffinity|topologySpreadConstraints
```

**Potential Solutions**:
- Use AWS placement groups, GCP instance placement, or Azure proximity placement groups
- Co-locate tightly coupled services in the same availability zone
- Use Kubernetes pod affinity rules to schedule related pods together
- Evaluate whether cross-AZ redundancy is truly needed per service

### 9.2 Reduce Transmitted Data

**Summary**: Transmit only necessary data fields/properties rather than full objects. Choose efficient serialization formats — Protobuf is significantly more compact than XML/JSON.

**Grep Patterns** (find over-fetching or verbose serialization):
```
# SELECT * queries (fetching all columns)
SELECT\s+\*\s+FROM
# Returning full objects from APIs
return\s+.*\.to_dict\(\)|return\s+.*\.serialize\(|res\.json\(.*\)
# JSON serialization of large objects
json\.dumps|JSON\.stringify|ObjectMapper|Gson
# Missing GraphQL or field-selection in REST
fields=|select=|\$select=
# XML usage where binary formats exist
application/xml|text/xml|\.xml
```

**Potential Solutions**:
- Use field selection in queries (`SELECT col1, col2` instead of `SELECT *`)
- Implement GraphQL or sparse fieldsets for REST APIs (`?fields=id,name`)
- Use Protobuf, MessagePack, or FlatBuffers instead of JSON/XML for internal APIs
- Implement pagination for list endpoints
- Strip unnecessary metadata from API responses

---

## 10. Async & Queue-Based Processing

### 10.1 Use Asynchronous Network Calls

**Summary**: Replace synchronous blocking calls with async patterns (async/await, event loops). Blocked threads waste CPU cycles waiting for I/O responses. Async allows the CPU to do other work during waits, reducing energy consumption.

**Grep Patterns** (find synchronous blocking calls):
```
# Synchronous HTTP clients
requests\.get\(|requests\.post\(|HttpURLConnection|urllib\.request
# Blocking database calls without async
cursor\.execute|\.query\(.*\)(?!.*await)|session\.execute(?!.*await)
# Thread.sleep or blocking waits
Thread\.sleep|time\.sleep|sync\.WaitGroup
# Missing async/await patterns
def\s+\w+\((?!.*async)|function\s+\w+\((?!.*async)
```

**Potential Solutions**:
- Use async HTTP clients (`aiohttp`, `httpx`, `fetch`, async OkHttp)
- Adopt async database drivers (asyncpg, motor, r2dbc)
- Use `async/await` patterns in Python, JavaScript/TypeScript, C#, Rust
- Implement event-driven architectures with message brokers

### 10.2 Queue Non-Urgent Processing Requests

**Summary**: Defer non-critical work (batch processing, reports, cleanup) using message queues instead of processing everything immediately. Smooths out resource utilization and reduces idle standby resources.

**Grep Patterns** (find synchronous processing of non-urgent work):
```
# Inline report generation or email sending
send_email\(|generate_report\(|export_\w+\(
# Synchronous batch processing
for.*in.*all\(\)|\.findAll\(\)|bulk_
# Heavy processing in HTTP request handlers
@app\.route.*\n.*process_|@PostMapping.*\n.*compute_
# Missing queue/worker patterns
celery|rq\.|bull|sidekiq|SQS|RabbitMQ|kafka
```

**Potential Solutions**:
- Offload non-urgent work to message queues (SQS, RabbitMQ, Kafka, Redis Queue)
- Use task queues (Celery, Bull, Sidekiq) for background processing
- Implement the producer-consumer pattern for batch operations
- Process queued work during off-peak hours for additional energy savings

---

## 11. Resilience Patterns

### 11.1 Use Circuit Breaker Patterns

**Summary**: Prevent repeated requests to unavailable services. When health checks fail, the circuit breaker stops making requests and retries after a cooldown. Eliminates wasted energy from futile network calls.

**Grep Patterns** (find retry-without-breaker patterns):
```
# Unbounded retries without circuit breaker
retry\(|@Retryable|retries\s*=|max_retries
# Missing circuit breaker libraries
CircuitBreaker|circuitbreaker|resilience4j|polly|hystrix
# Hardcoded retry loops
while.*retry|for.*attempt|except.*continue
# Health check endpoints
/health|/healthz|/ready|/live
```

**Potential Solutions**:
- Implement circuit breakers using libraries (resilience4j, Polly, pybreaker, opossum)
- Configure health check endpoints and integrate with circuit breaker state
- Add exponential backoff to retry mechanisms
- Set reasonable timeout limits on outgoing HTTP calls

### 11.2 Shed Lower Priority Traffic

**Summary**: Selectively drop non-critical requests during resource constraints or high carbon intensity periods rather than scaling up to handle all traffic. Use exponential shedding policies.

**Grep Patterns** (find missing traffic prioritization):
```
# Rate limiting without priority awareness
rate_limit|RateLimit|throttle|quota
# Missing request priority classification
priority|Priority|x-priority|importance
# Load balancer configs without shedding
upstream|backend.*server|target_group
# Missing graceful degradation
circuit_breaker|fallback|degraded
```

**Potential Solutions**:
- Classify traffic into priority tiers (critical, normal, best-effort)
- Implement priority-based rate limiting at the API gateway level
- Use load shedding middleware that drops low-priority requests under pressure
- Return cached or degraded responses for non-critical features during high load

---

## 12. Environment & Resource Lifecycle

### 12.1 Minimize Total Deployed Environments

**Summary**: Reduce the number of separate deployment environments (dev, staging, QA, perf-test, production). Each environment has an incremental energy cost. Consolidate environments to serve multiple purposes.

**Grep Patterns** (find excessive environments):
```
# Multiple environment definitions
environment\s*=\s*"(dev|staging|qa|uat|perf|load-test|demo|sandbox)"
# Terraform workspaces or env-specific configs
terraform\.workspace|var\.environment|ENV\s*=
# Multiple namespace definitions for environments
namespace:\s*(dev|staging|qa|uat|perf|preprod)
# Duplicated infrastructure modules per environment
module\s+".*-(dev|staging|qa|prod)"
```

**Potential Solutions**:
- Consolidate QA + performance testing into a single environment
- Use ephemeral environments (spin up on demand, destroy after use) via CI/CD
- Share dev/staging clusters with namespace isolation
- Implement feature flags to test in production safely

### 12.2 Remove Unused Assets

**Summary**: Identify and decommission cloud resources no longer actively used. Consolidate underutilized resources and clean up generated assets.

**Grep Patterns** (find potentially unused resources):
```
# Commented-out resource definitions
#\s*resource\s+"|//\s*resource\s+"
# Resources with no references
output\s+".*".*\{|data\s+".*".*\{
# Unused Docker images or tags
COPY.*unused|\.dockerignore
# Old migration files or deprecated code
deprecated|DEPRECATED|@deprecated|# TODO.*remove
```

**Potential Solutions**:
- Run cloud cost analysis tools to find unused resources (AWS Trusted Advisor, GCP Recommender)
- Audit IaC for resources that exist in code but serve no current purpose
- Set up automated unused resource detection (e.g., AWS Config rules)
- Implement resource tagging and ownership policies for accountability

---

## 13. Security as Sustainability

### 13.1 Scan for Vulnerabilities

**Summary**: Attackers exploit unpatched systems to hijack cloud resources (cryptomining, botnets), causing massive unnecessary energy consumption. Vulnerability scanning and EDR tools prevent this wasteful resource abuse.

**Grep Patterns** (find missing security scanning):
```
# CI/CD without security scanning steps
\.github/workflows|\.gitlab-ci|Jenkinsfile|pipeline
# Missing container scanning
trivy|snyk|grype|anchore|clair
# Outdated dependencies
requirements\.txt|package\.json|go\.mod|Cargo\.toml
# Missing security headers
Content-Security-Policy|X-Frame-Options|Strict-Transport-Security
```

**Potential Solutions**:
- Add container image scanning to CI/CD pipelines (Trivy, Snyk, Grype)
- Enable dependency vulnerability scanning (Dependabot, Renovate, Snyk)
- Deploy runtime threat detection (Falco, GuardDuty, Security Command Center)
- Implement automated patching workflows

### 13.2 Use Cloud Native Network Security Tools

**Summary**: Deploy network and web application firewalls using cloud-native tools that scale dynamically with demand. Filter malicious traffic at the source to prevent wasteful processing.

**Grep Patterns** (find missing network security):
```
# Missing WAF configuration
aws_wafv2|google_compute_security_policy|azurerm_web_application_firewall
# Missing network policies in Kubernetes
kind:\s*NetworkPolicy
# Open security groups / firewall rules
ingress.*0\.0\.0\.0/0|source_ranges.*0\.0\.0\.0/0
# Missing egress filtering
egress|outbound|destination
```

**Potential Solutions**:
- Deploy cloud-native WAF (AWS WAF, Cloud Armor, Azure WAF)
- Implement Kubernetes NetworkPolicies to restrict pod-to-pod traffic
- Restrict security group rules to specific IP ranges and ports
- Enable egress filtering to prevent data exfiltration and botnet communication

### 13.3 Use DDoS Protection

**Summary**: DDoS attacks flood servers with malicious traffic, wasting computational resources and energy on nonsensical requests. Cloud-native DDoS protection blocks this wasteful traffic.

**Grep Patterns** (find missing DDoS protection):
```
# Public-facing load balancers without DDoS protection
resource\s+"aws_lb"|resource\s+"google_compute_forwarding_rule"|resource\s+"azurerm_lb"
# Missing DDoS protection resources
aws_shield|google_compute_security_policy|azurerm_network_ddos_protection_plan
# CloudFlare or other CDN/proxy config
cloudflare|cloudfront|fastly
```

**Potential Solutions**:
- Enable AWS Shield (Standard is free; Advanced for critical workloads)
- Configure GCP Cloud Armor policies
- Enable Azure DDoS Protection Plan
- Use CDN/proxy services (CloudFlare, Fastly) as DDoS mitigation layer

---

## 14. Time-Shifting & Carbon-Aware Scheduling

### 14.1 Time-Shift Kubernetes Cron Jobs

**Summary**: Schedule flexible batch jobs (ML training, ETL, reports) during periods of lower electricity carbon intensity using 24-hour forecasts. No code changes needed — operates at the platform level.

**Grep Patterns** (find fixed-schedule batch jobs):
```
# Kubernetes CronJobs with fixed schedules
kind:\s*CronJob
schedule:\s*"[0-9]
# Fixed cron expressions
cron\(|schedule\s*=\s*"cron|schedule_expression
# Batch processing jobs
kind:\s*Job\b
# Missing carbon-intensity awareness
carbon|intensity|grid|watt-time|electricitymap
```

**Potential Solutions**:
- Use carbon-aware SDKs (Carbon Aware SDK by Green Software Foundation) to choose low-carbon windows
- Integrate with electricity carbon intensity APIs (WattTime, Electricity Maps)
- Set flexible deadline windows for non-urgent jobs (e.g., "run within the next 12 hours")
- Use KEDA with carbon-intensity-based triggers

---

## 15. Language & Compilation

### 15.1 Use Compiled Languages

**Summary**: Compiled languages (Go, Rust, C, C++) or ahead-of-time compilation (GraalVM native image for Java/Python) consume less energy at runtime than interpreted languages. Compiled binaries are also smaller, reducing storage/transfer overhead.

**Grep Patterns** (find interpreted language usage in hot paths):
```
# Python/Ruby/PHP in performance-critical services
#!/usr/bin/(python|ruby|php)|from\s+flask|require\s+'sinatra'
# Missing native compilation for JVM languages
-jar\s+|java\s+-cp|spring-boot
# Node.js for CPU-bound tasks
require\('cluster'\)|worker_threads|child_process\.fork
# Missing GraalVM native image config
native-image|graalvm|quarkus\.native
```

**Potential Solutions**:
- Consider Go or Rust for new performance-critical microservices
- Use GraalVM native image for existing Java/Kotlin/Scala applications (Quarkus, Micronaut)
- Compile Python to native with Cython or Nuitka for CPU-bound tasks
- Use WebAssembly (Wasm) for portable compiled execution
- Benchmark energy consumption before and after to validate gains

---

## 16. Customer-Side Impact

### 16.1 Optimize Impact on Customer Devices and Equipment

**Summary**: Design software compatible with older devices, browsers, and OS versions to extend customer hardware lifespan. Reducing forced hardware upgrades lowers embodied carbon from device manufacturing.

**Grep Patterns** (find patterns that force hardware upgrades):
```
# Aggressive minimum browser/OS requirements
browserslist|"not ie|"not dead"|engines.*node.*>=\s*(18|20)
# Heavy client-side frameworks without optimization
bundle.*size|webpack.*config|chunk.*size
# Missing progressive enhancement
@supports|@media|feature.detection|Modernizr
# Large JavaScript bundles
import.*from\s+['"](?!\.)|require\(['"](?!\.)
```

**Potential Solutions**:
- Set inclusive `browserslist` targets to support older browsers
- Implement progressive enhancement (core functionality works without JS/modern CSS)
- Optimize bundle sizes with tree-shaking, code splitting, and lazy loading
- Compress images and use modern formats (WebP, AVIF) with fallbacks
- Test on low-end devices and throttled network connections

---

## Quick Reference: Pattern to Grep Cheat Sheet

| Pattern Category | Key Grep Target | File Types |
|---|---|---|
| Caching | `Cache-Control`, CDN resources | `*.conf`, `*.yaml`, `*.tf` |
| Compression | `gzip`, `brotli`, `Content-Encoding` | `*.conf`, `*.py`, `*.ts` |
| Containerization | `FROM`, `Dockerfile`, VM resources | `Dockerfile`, `*.tf`, `*.yaml` |
| Storage | lifecycle, retention, `aws_ebs_volume` | `*.tf`, `*.yaml`, `*.json` |
| Encryption | `ssl_context`, `tls`, `encrypt` | `*.py`, `*.java`, `*.yaml` |
| CPU/Hardware | `instance_type`, `machine_type`, `vm_size` | `*.tf`, `*.yaml` |
| Stateless | `session`, `sticky`, `lru_cache` | `*.py`, `*.java`, `*.ts` |
| Scaling | `replicas`, `HPA`, `autoscaling` | `*.yaml`, `*.tf` |
| Network | `SELECT *`, `json.dumps`, `placement_group` | `*.py`, `*.sql`, `*.tf` |
| Async/Queues | `requests.get`, `Thread.sleep`, `celery` | `*.py`, `*.java`, `*.ts` |
| Resilience | `retry`, `CircuitBreaker`, `rate_limit` | `*.py`, `*.java`, `*.ts` |
| Environments | `environment =`, `namespace:` | `*.tf`, `*.yaml` |
| Security | `trivy`, `NetworkPolicy`, `aws_wafv2` | `*.yaml`, `*.tf`, CI files |
| Time-shifting | `CronJob`, `schedule:`, `carbon` | `*.yaml`, `*.tf` |
| Compilation | `#!/usr/bin/python`, `native-image` | `Dockerfile`, `*.py`, `*.java` |
| Customer impact | `browserslist`, `bundle`, `@supports` | `*.json`, `*.js`, `*.css` |

---

## Sources

- [Green Software Foundation — Cloud Patterns Catalog](https://patterns.greensoftware.foundation/catalog/cloud/)
- [Software Carbon Intensity (SCI) Specification](https://sci.greensoftware.foundation/)
