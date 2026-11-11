# System & Application Observability Platform

A complete observability stack combining host and HTTP application metrics with Prometheus, Kubernetes workload log aggregation using MicroK8s, Grafana Alloy, and Loki, real-time dashboards in Grafana, and automated email alerting over SMTP.

## Table of Contents

- [1. Architecture & Data Flow](#1-architecture--data-flow)
- [2. Repository Layout](#2-repository-layout)
- [3. Environment Setup (Local Ubuntu / Vagrant VM / AWS EC2)](#3-environment-setup-local-ubuntu--vagrant-vm--aws-ec2)
- [4. Deploying the Docker Compose Backend](#4-deploying-the-docker-compose-backend)
- [5. Deploying the MicroK8s Workload & Grafana Alloy](#5-deploying-the-microk8s-workload--grafana-alloy)
- [6. Traffic Testing, PromQL Queries & Host Cross-Checks](#6-traffic-testing-promql-queries--host-cross-checks)
- [7. Testing Email Alerting](#7-testing-email-alerting)
- [8. Limitations & Production Improvements](#8-limitations--production-improvements)
- [9. Cleanup Instructions](#9-cleanup-instructions)
- [10. Verification & Evidence Gallery](#10-verification--evidence-gallery)

---

## 1. Architecture & Data Flow

The platform runs across two connected runtime environments on an Ubuntu host:

```text
+-------------------------------------------------------------------------+
| Ubuntu Host / VM / EC2 Instance                                         |
|                                                                         |
|  +-----------------------------------+   +---------------------------+  |
|  | DOCKER COMPOSE STACK              |   | MICROK8S CLUSTER          |  |
|  |                                   |   | (Namespace: obs-workload) |  |
|  |  [Order HTTP API] --+             |   |                           |  |
|  |   (:18000/metrics)  |             |   |  [order-worker Pod]       |  |
|  |                     v             |   |   (stdout INFO / stderr)  |  |
|  |  [Node Exporter] -> [Prometheus]  |   |             |             |  |
|  |   (:9100/metrics)    (:19090)     |   |             v             |  |
|  |                         |         |   |      [Grafana Alloy]      |  |
|  |                         v         |   |             |             |  |
|  |                     [Grafana] <---+--- [Loki] <-----+             |  |
|  |                      (:13000)     |    (:3100 /loki/api/v1/push)  |  |
|  |                         |         |                               |  |
|  +-------------------------|---------+   +---------------------------+  |
|                            v                                            |
|               [Outbound SMTP / Mailpit]                                 |
|                            |                                            |
|                            v                                            |
|                   [Recipient Inbox]                                     |
+-------------------------------------------------------------------------+
```

1. **Metrics Pipeline:**
   - **Node Exporter:** Mounts the Ubuntu host's `/proc`, `/sys`, and `/` in read-only mode to expose real hardware and OS telemetry.
   - **Order HTTP API:** A FastAPI service exposing `GET /health`, `POST /api/orders`, and `GET /metrics`. It tracks request counts (`http_requests_total`), request latency histograms (`http_request_duration_seconds`), and business order outcomes (`orders_created_total`).
   - **Prometheus:** Scrapes both targets every `15s` and stores time-series data on a persistent Docker volume.
2. **Kubernetes Logging Pipeline:**
   - **MicroK8s Workload:** The `order-worker` Deployment runs in the `obs-workload` namespace, writing structured `INFO` events to `stdout` and simulated payment gateway `ERROR` events (`PAY_504`) to `stderr`.
   - **Grafana Alloy & Loki:** Alloy runs inside MicroK8s, discovers pod logs across the cluster, attaches Kubernetes metadata labels (`namespace`, `pod`, `container`, `app`), and forwards log streams over the host network bridge to Loki on port `3100`.
3. **Visualization & Alerting:**
   - **Grafana:** Automatically provisions Prometheus and Loki data sources, a 9-panel operational dashboard, and the `OrderAPITargetDown` alert rule.
   - **SMTP Delivery:** Uses environment variables injected from `.env` (kept out of Git via `.gitignore`) to deliver email notifications through Gmail SMTP or the bundled Mailpit server.

---

## 2. Repository Layout

```text
.
├── README.md
├── compose.yaml
├── .env.example
├── .gitignore
├── .gitattributes
├── app/
│   ├── Dockerfile
│   ├── main.py
│   └── requirements.txt
├── prometheus/
│   └── prometheus.yml
├── loki/
│   └── config.yml
├── kubernetes/
│   ├── namespace.yaml
│   ├── workload.yaml
│   └── alloy-values.yaml
├── grafana/
│   ├── dashboards/
│   │   └── observability-overview.json
│   └── provisioning/
│       ├── alerting/
│       │   └── alerting.yml
│       ├── dashboards/
│       │   └── dashboards.yml
│       └── datasources/
│           └── datasources.yml
├── alerting/
│   └── configuration-notes.md
├── scripts/
│   └── traffic-test.sh
└── evidence/
    ├── 01. app-traffic-metrics.png
    ├── 02. compose-and-cluster.png
    ├── 03. prometheus-targets.png
    ├── 04. promql-and-crosschecks.png
    ├── 05. k8s-cluster-and-logs.png
    ├── 06. kubernetes-logs.png.jpeg
    ├── 07. grafana-metrics.png
    ├── 08. grafana-metrics.png
    ├── 09. email-alert.png
    └── 10. alert-rule.png
```

---

## 3. Environment Setup (Local Ubuntu / Vagrant VM / AWS EC2)

You can run this project on a native Ubuntu laptop, inside a Vagrant VirtualBox VM on Windows/macOS, or on an AWS EC2 instance (`t3.large` recommended: 2+ vCPUs, 8 GB RAM, 30 GB disk).

### Option A: Local Ubuntu Machine or AWS EC2 Instance

Run these commands on a fresh Ubuntu system to install Docker Engine, Docker Compose v2, and MicroK8s:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git docker.io docker-compose-v2

sudo usermod -aG docker $USER

sudo snap install microk8s --classic
sudo usermod -aG microk8s $USER
mkdir -p ~/.kube
sudo chown -R $USER ~/.kube

newgrp docker
newgrp microk8s

microk8s status --wait-ready
microk8s enable dns helm3 hostpath-storage
```

> **Note for AWS EC2 Users:** To keep all observability ports private to your laptop instead of opening them to the public internet in your EC2 Security Group, connect to your EC2 instance using SSH local port forwarding from your laptop terminal:
>
> ```bash
> ssh -i your-key.pem \
>   -L 13000:127.0.0.1:13000 \
>   -L 19090:127.0.0.1:19090 \
>   -L 18000:127.0.0.1:18000 \
>   -L 18025:127.0.0.1:18025 \
>   ubuntu@<EC2-PUBLIC-IP>
> ```

### Option B: Windows / macOS with Vagrant VM

If you are using Vagrant with VirtualBox, forward ports `13000` (Grafana), `19090` (Prometheus), `18000` (Order API), and `18025` (Mailpit) to `127.0.0.1` on the host, assign private IP `192.168.56.60`, and connect via:

```bash
vagrant up
vagrant ssh
```

---

## 4. Deploying the Docker Compose Backend

### Step 1: Clone the Repository and Configure `.env`

```bash
git clone https://github.com/Adnan-Sarkar/k8s-observability-platform.git ~/observability-assessment
cd ~/observability-assessment

cp .env.example .env
chmod +x scripts/traffic-test.sh
```

Edit `.env` if you want to use your own Gmail App Password for real email delivery, or keep `GF_SMTP_HOST=mailpit:1025` to test with the built-in Mailpit inbox:

```bash
nano .env
```

### Step 2: Launch the Containers

```bash
sudo iptables -P FORWARD ACCEPT
docker compose config -q && echo "Compose configuration valid"
docker compose up -d --build
docker compose ps
```

### Service Endpoints (Accessible Locally)

| Service               | Local URL                        | Credentials / Notes                             |
| :-------------------- | :------------------------------- | :---------------------------------------------- |
| **Order API Health**  | `http://127.0.0.1:18000/health`  | Returns `{"status":"ok"}`                       |
| **Order API Metrics** | `http://127.0.0.1:18000/metrics` | Prometheus metrics exposition                   |
| **Prometheus UI**     | `http://127.0.0.1:19090/targets` | Check `order_http_app` & `ubuntu_node_exporter` |
| **Grafana UI**        | `http://127.0.0.1:13000`         | Default: `admin` / `changeme`                   |
| **Mailpit Web Inbox** | `http://127.0.0.1:18025`         | Local SMTP test inbox                           |

---

## 5. Deploying the MicroK8s Workload & Grafana Alloy

### Step 1: Verify the Host IP for Loki Ingestion

By default, `kubernetes/alloy-values.yaml` sends logs to `http://192.168.56.60:3100/loki/api/v1/push` (the Vagrant VM private network IP).

- If you are running on **Local Ubuntu or AWS EC2** instead of Vagrant, update the IP in `kubernetes/alloy-values.yaml` to match your machine's primary private IP before deploying Alloy:
  ```bash
  HOST_IP=$(hostname -I | awk '{print $1}')
  sed -i "s/192.168.56.60/${HOST_IP}/g" kubernetes/alloy-values.yaml
  ```

### Step 2: Deploy the Namespace and Workload Pod

```bash
microk8s kubectl apply -f kubernetes/namespace.yaml
microk8s kubectl apply -f kubernetes/workload.yaml

microk8s kubectl wait --for=condition=ready pod -l app=order-worker -n obs-workload --timeout=90s
microk8s kubectl logs -n obs-workload -l app=order-worker --tail=10
```

### Step 3: Deploy Grafana Alloy via Helm

```bash
microk8s helm3 repo add grafana [https://grafana.github.io/helm-charts](https://grafana.github.io/helm-charts)
microk8s helm3 repo update

microk8s helm3 upgrade --install alloy grafana/alloy \
  -n obs-workload \
  -f kubernetes/alloy-values.yaml

microk8s kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=alloy -n obs-workload --timeout=180s
```

### Step 4: Verify Log Ingestion in Loki & Grafana Explore

```bash
curl -s http://localhost:3100/loki/api/v1/label/namespace/values
```

Open Grafana Explore (`http://127.0.0.1:13000/explore`), select the **Loki** data source, and run:

```logql
{namespace="obs-workload", app="order-worker"}
```

---

## 6. Traffic Testing, PromQL Queries & Host Cross-Checks

### Generate Live Application Traffic & Errors

Run the traffic generator script to send 20 normal order requests (`HTTP 200`) and 8 simulated failure requests (`HTTP 500`):

```bash
./scripts/traffic-test.sh
```

### Core PromQL Queries Used in Prometheus & Grafana

1. **Ubuntu Host CPU Utilization (%):**
   ```promql
   100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[1m])) * 100)
   ```
2. **Ubuntu Host RAM Utilization (%):**
   ```promql
   (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100
   ```
3. **Application Requests / Second:**
   ```promql
   sum by (endpoint, status) (rate(http_requests_total[1m]))
   ```
4. **Application HTTP 5xx Error Rate (%):**
   ```promql
   (sum(rate(http_requests_total{status=~"5.."}[1m])) / clamp_min(sum(rate(http_requests_total[1m])), 0.0001)) * 100
   ```
5. **Application p95 Request Latency (Seconds):**
   ```promql
   histogram_quantile(0.95, sum by (le, endpoint) (rate(http_request_duration_seconds_bucket[1m])))
   ```

### Cross-Check Host Metrics Against Linux Commands

Run this block to compare Prometheus API readings directly with Linux system utilities (`free`, `df`, and `uptime`):

```bash
echo "=== 1. PromQL: Host CPU % ==="
curl -sG http://localhost:19090/api/v1/query --data-urlencode 'query=100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[1m])) * 100)' | grep -o '"value":\[[^]]*\]'
echo "=== 2. PromQL: Host RAM % ==="
curl -sG http://localhost:19090/api/v1/query --data-urlencode 'query=(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100' | grep -o '"value":\[[^]]*\]'
echo "=== 3. PromQL: App Requests/sec ==="
curl -sG http://localhost:19090/api/v1/query --data-urlencode 'query=sum(rate(http_requests_total[1m]))' | grep -o '"value":\[[^]]*\]'
echo "=== 4. PromQL: App Error Rate % ==="
curl -sG http://localhost:19090/api/v1/query --data-urlencode 'query=(sum(rate(http_requests_total{status=~"5.."}[1m])) / sum(rate(http_requests_total[1m]))) * 100' | grep -o '"value":\[[^]]*\]'
echo "=== 5. PromQL: App p95 Latency (s) ==="
curl -sG http://localhost:19090/api/v1/query --data-urlencode 'query=histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket[1m])))' | grep -o '"value":\[[^]]*\]'
echo "=== 6. Ubuntu Host Cross-Checks (free, df, uptime) ==="
free -m && df -h / && uptime
```

---

## 7. Testing Email Alerting

The `OrderAPITargetDown` alert rule (`grafana/provisioning/alerting/alerting.yml`) evaluates `up{job="order_http_app"} < 1` every `10s` with a `20s` pending period and routes notifications to the `ops-email-inbox` contact point. Full runbook details are documented in [`alerting/configuration-notes.md`](alerting/configuration-notes.md).

### Trigger the Alert Safely

```bash
# 1. Stop the Order API container to simulate an outage
docker compose stop order-app

# 2. Wait 45 seconds for Prometheus scrape + Grafana 20s pending evaluation
sleep 45

# 3. Check Grafana Alerting UI ([http://127.0.0.1:13000/alerting/list](http://127.0.0.1:13000/alerting/list)) and your email inbox

# 4. Start the Order API container back up to resolve the alert
docker compose start order-app
```

---

## 8. Limitations & Production Improvements

- **Single-Instance Loki Storage:** Loki currently stores chunks and indexes on a local Docker volume. In a multi-node production cluster, configuring Grafana Alloy with a write-ahead log (WAL) and backing Loki with S3/MinIO object storage prevents data loss during node failures.
- **Plaintext Internal Traffic:** Traffic between Grafana Alloy (`MicroK8s`) and Loki (`Docker Compose`) traverses the private host interface over HTTP. Production deployments should enforce mutual TLS (mTLS) and tenant authentication headers (`X-Scope-OrgID`).

---

## 9. Cleanup Instructions

To remove all Kubernetes resources, Docker containers, networks, and volumes cleanly:

```bash
# Remove Grafana Alloy, workload deployment, and namespace from MicroK8s
microk8s helm3 uninstall alloy -n obs-workload
microk8s kubectl delete -f kubernetes/workload.yaml
microk8s kubectl delete -f kubernetes/namespace.yaml

# Stop and remove Docker Compose stack and volumes
docker compose down -v
```

---

## 10. Verification & Evidence Gallery

### 01. Application Traffic & Before/After Metrics (`01. app-traffic-metrics.png`)

![01. Application Traffic & Metrics](evidence/01.%20app-traffic-metrics.png)

### 02. Ubuntu Environment, Docker Compose & MicroK8s Status (`02. compose-and-cluster.png`)

![02. Compose and Cluster Status](evidence/02.%20compose-and-cluster.png)

### 03. Prometheus Scrape Targets UP (`03. prometheus-targets.png`)

![03. Prometheus Targets](evidence/03.%20prometheus-targets.png)

### 04. Five PromQL Expressions & Ubuntu Host Cross-Checks (`04. promql-and-crosschecks.png`)

![04. PromQL and Cross-Checks](evidence/04.%20promql-and-crosschecks.png)

### 05. MicroK8s Workload Pods, Container Logs & Loki Ingestion (`05. k8s-cluster-and-logs.png`)

![05. MicroK8s Cluster and Logs](evidence/05.%20k8s-cluster-and-logs.png)

### 06. Kubernetes Pod Logs Filtered in Grafana Explore (`06. kubernetes-logs.png.jpeg`)

![06. Kubernetes Logs in Grafana Explore](evidence/06.%20kubernetes-logs.png.jpeg)

### 07. Operational Grafana Dashboard — Baseline View (`07. grafana-metrics.png`)

![07. Grafana Dashboard Baseline](evidence/07.%20grafana-metrics.png)

### 08. Operational Grafana Dashboard — Live Traffic & Error Spikes (`08. grafana-metrics.png`)

![08. Grafana Dashboard Live Spikes](evidence/08.%20grafana-metrics.png)

### 09. Received SMTP Alert Email in Inbox (`09. email-alert.png`)

![09. Received Email Alert](evidence/09.%20email-alert.png)

### 10. Grafana Alert Rule & Firing State (`10. alert-rule.png`)

![10. Grafana Alert Rule State](evidence/10.%20alert-rule.png)
