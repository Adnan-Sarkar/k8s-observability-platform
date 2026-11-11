#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-http://127.0.0.1:18000}"

echo "=== 1. Checking /health ==="
curl -s "${API_URL}/health"
echo -e "\n"

echo "=== 2. Metrics BEFORE Traffic ==="
curl -s "${API_URL}/metrics" | grep -E "^(http_requests_total|orders_created_total|http_request_duration_seconds_count)" || true
echo ""

echo "=== 3. Sending 20 Normal Orders ==="
for i in $(seq 1 20); do
  ITEM=$(shuf -n1 -e laptop monitor keyboard mouse)
  curl -s -o /dev/null -w "Normal Order #$i ($ITEM) -> HTTP %{http_code}\n" \
    -X POST "${API_URL}/api/orders" \
    -H "Content-Type: application/json" \
    -d "{\"item\": \"${ITEM}\", \"quantity\": 2, \"simulate_error\": false}"
  sleep 0.15
done
echo ""

echo "=== 4. Sending 8 Deliberate Failure Orders ==="
for i in $(seq 1 8); do
  curl -s -o /dev/null -w "Failed Order #$i -> HTTP %{http_code}\n" \
    -X POST "${API_URL}/api/orders" \
    -H "Content-Type: application/json" \
    -d '{"item": "laptop", "quantity": 1, "simulate_error": true}'
  sleep 0.15
done
echo ""

echo "=== 5. Metrics AFTER Traffic ==="
curl -s "${API_URL}/metrics" | grep -E "^(http_requests_total|orders_created_total|http_request_duration_seconds_count)"