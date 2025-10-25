from fastapi import FastAPI
import psycopg2
import redis
import time
import os

# OpenTelemetry imports
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor

# Configure OpenTelemetry
resource = Resource.create({
    "service.name": os.getenv("OTEL_SERVICE_NAME", "fastapi-app"),
    "service.version": "1.0.0",
})

# Set up tracer provider
tracer_provider = TracerProvider(resource=resource)
trace.set_tracer_provider(tracer_provider)

# Configure OTLP exporter
otlp_exporter = OTLPSpanExporter(
    endpoint=f"{os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT', 'http://tempo:4318')}/v1/traces",
)
tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

# Instrument database and cache libraries
Psycopg2Instrumentor().instrument()
RedisInstrumentor().instrument()

app = FastAPI(
    title="VPS Test API",
    root_path="/api"
)

# Instrument FastAPI
FastAPIInstrumentor.instrument_app(app)

@app.get("/")
async def root():
    # Get current trace context
    current_span = trace.get_current_span()
    trace_id = format(current_span.get_span_context().trace_id, '032x') if current_span else None

    return {
        "message": "FastAPI is running!",
        "timestamp": time.time(),
        "trace_id": trace_id
    }

@app.get("/health")
async def health():
    health_status = {
        "status": "healthy",
        "service": "fastapi",
        "timestamp": time.time()
    }
    
    # Test database connection
    try:
        conn = psycopg2.connect(os.getenv("DATABASE_URL"))
        conn.close()
        health_status["database"] = "connected"
    except Exception as e:
        health_status["database"] = f"error: {str(e)}"
    
    # Test Redis connection
    try:
        r = redis.from_url(os.getenv("REDIS_URL"))
        r.ping()
        health_status["redis"] = "connected"
    except Exception as e:
        health_status["redis"] = f"error: {str(e)}"
    
    return health_status

@app.get("/stress")
async def stress_test():
    # Get current trace context
    current_span = trace.get_current_span()
    trace_id = format(current_span.get_span_context().trace_id, '032x') if current_span else None

    # Add a span for the computation
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("heavy_computation"):
        result = sum(i * i for i in range(1000000))

    return {
        "result": result,
        "message": "Stress test completed",
        "trace_id": trace_id
    }
