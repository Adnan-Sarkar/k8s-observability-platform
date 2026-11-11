import time
import random
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

app = FastAPI(title="Order API")

# 1. Request Counter (bounded labels: method, endpoint, status)
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests processed",
    ["method", "endpoint", "status"]
)

# 2. Request Latency Histogram (in seconds)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5]
)

# 3. Business-Event Counter (orders processed by category and result)
ORDERS_CREATED_TOTAL = Counter(
    "orders_created_total",
    "Total business orders processed",
    ["item_category", "result"]
)

class OrderPayload(BaseModel):
    item: str = "laptop"
    quantity: int = 1
    simulate_error: bool = False

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    if request.url.path == "/metrics":
        return await call_next(request)
    
    start_time = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        duration = time.perf_counter() - start_time
        endpoint = request.url.path if request.url.path in ["/health", "/api/orders"] else "other"
        HTTP_REQUESTS_TOTAL.labels(
            method=request.method,
            endpoint=endpoint,
            status=str(status_code)
        ).inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(
            method=request.method,
            endpoint=endpoint
        ).observe(duration)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/orders")
def create_order(order: OrderPayload):
    time.sleep(random.uniform(0.015, 0.35))
    
    AllowedItems = {"laptop", "monitor", "keyboard", "mouse"}
    category = order.item.lower() if order.item.lower() in AllowedItems else "other"

    if order.simulate_error or order.quantity <= 0:
        ORDERS_CREATED_TOTAL.labels(item_category=category, result="failed").inc()
        raise HTTPException(status_code=500, detail="Simulated order processing failure")
    
    ORDERS_CREATED_TOTAL.labels(item_category=category, result="success").inc()
    return {
        "order_status": "created",
        "item": category,
        "quantity": order.quantity
    }

@app.get("/metrics")
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)