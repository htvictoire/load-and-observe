from fastapi import FastAPI
import psycopg2
import redis
import time
import os

app = FastAPI(title="VPS Test API")

@app.get("/")
async def root():
    return {"message": "FastAPI is running!", "timestamp": time.time()}

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
    # Simulate some CPU work
    result = sum(i * i for i in range(1000000))
    return {"result": result, "message": "Stress test completed"}
