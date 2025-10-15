from celery import Celery
import os

app = Celery('tasks', broker=os.getenv('REDIS_URL', 'redis://redis:6379'))

@app.task
def process_data(data):
    # Simulate heavy processing
    import time
    time.sleep(2)
    return {"processed": data, "status": "complete"}
