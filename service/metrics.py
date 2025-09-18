# service/metrics.py
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

HTTP_REQS = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"]
)

HTTP_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency (seconds)",
    ["method", "path"]
)

def register_metrics(app):
    @app.middleware("http")
    async def prometheus_middleware(request, call_next):
        import time
        method = request.method
        path = request.url.path
        t0 = time.perf_counter()
        resp = await call_next(request)
        dt = time.perf_counter() - t0
        HTTP_LATENCY.labels(method, path).observe(dt)
        HTTP_REQS.labels(method, path, str(resp.status_code)).inc()
        return resp

    @app.get("/metrics")
    def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
