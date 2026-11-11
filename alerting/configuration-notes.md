# Alerting Configuration and Operator Runbook

## 1. Outbound SMTP Configuration

- **Delivery Method:** Grafana outbound SMTP configured via environment variables in `.env` (`GF_SMTP_ENABLED=true`, `GF_SMTP_HOST=smtp.gmail.com:587`, `GF_SMTP_USER`, `GF_SMTP_PASSWORD`, and `ALERT_RECIPIENT_EMAIL`).
- **Secret Hygiene:** No SMTP credentials, app passwords, or personal email addresses are stored in GitHub. `.env` is excluded via `.gitignore` and `.env.example` provides safe template variables.

## 2. Contact Point and Notification Policy

- **Contact Point Name:** `ops-email-inbox`
- **Recipient Variable:** `${ALERT_RECIPIENT_EMAIL}` (injected at container runtime from `.env`)
- **Notification Policy:** Default root policy routes alerts to `ops-email-inbox` with a `5s` group wait and `10s` group interval.

## 3. Alert Rule Specification

- **Rule Name:** `OrderAPITargetDown`
- **PromQL Expression:** `up{job="order_http_app"}`
- **Alert Threshold:** Fires when the latest value is `< 1` (`up == 0`), indicating the Order HTTP API container is unreachable.
- **Evaluation Duration:** Evaluated every `10s` with a `20s` pending (`for`) duration before transitioning to `Firing`.

## 4. Controlled Test Procedure

1. Stop the Order API container to simulate a service outage:
   `docker compose stop order-app`
2. Wait 35–45 seconds for Prometheus to mark `order_http_app` as `DOWN` and Grafana to transition `OrderAPITargetDown` to `Firing`.
3. Verify the delivered alert email in the designated Gmail inbox.
4. Restore the service:
   `docker compose start order-app`

## 5. Recommended Operator Action

1. Check container status and logs via `docker compose ps` and `docker compose logs --tail=50 order-app`.
2. Inspect Grafana Panel 5 (Requests/sec), Panel 6 (Error Rate), and Panel 9 (Workload Logs) to correlate the outage window.
3. Restart the `order-app` service (`docker compose up -d order-app`) and verify `GET /health` returns HTTP 200.
