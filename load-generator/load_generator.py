import requests
import time
import random
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import queue
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class LoadGenerator:
    def __init__(self):
        self.endpoints = [
            'http://nginx/',
            'http://fastapi-backend:8000/',
            'http://fastapi-backend:8000/health',
            'http://fastapi-backend:8000/stress',
            'http://nodejs-backend:3000/',
            'http://nodejs-backend:3000/health',
            'http://nodejs-backend:3000/stress',
        ]
        
        self.endpoint_weights = [10, 15, 20, 30, 15, 20, 30]
        
        self.stats = {
            'total_requests': 0,
            'successful': 0,
            'failed': 0,
            'timeouts': 0,
            'avg_response_time': 0,
            'max_response_time': 0,
            'min_response_time': float('inf'),
            'status_codes': {},
            'start_time': time.time()
        }
        self.lock = threading.Lock()
        self.response_times = queue.Queue(maxsize=1000)
        
        # Initialize InfluxDB client
        try:
            self.influx_client = InfluxDBClient(
                url="http://influxdb:8086",
                token="test-token-please-change",
                org="test-org"
            )
            self.write_api = self.influx_client.write_api(write_options=SYNCHRONOUS)
            logging.info("InfluxDB client initialized successfully")
        except Exception as e:
            logging.error(f"Failed to initialize InfluxDB client: {e}")
            self.influx_client = None
            self.write_api = None
    
    def write_to_influxdb(self, measurement, fields, tags=None):
        """Write metrics to InfluxDB"""
        if not self.write_api:
            return
        
        try:
            point = Point(measurement)
            
            if tags:
                for key, value in tags.items():
                    point = point.tag(key, value)
            
            for key, value in fields.items():
                point = point.field(key, value)
            
            self.write_api.write(bucket="load_test", record=point)
        except Exception as e:
            logging.error(f"Failed to write to InfluxDB: {e}")
    
    def make_request(self, url):
        """Make a single request and track stats"""
        try:
            start_time = time.time()
            response = requests.get(url, timeout=5)
            response_time = time.time() - start_time
            
            with self.lock:
                self.stats['total_requests'] += 1
                
                # Track status codes
                code = response.status_code
                self.stats['status_codes'][code] = self.stats['status_codes'].get(code, 0) + 1
                
                if response.status_code == 200:
                    self.stats['successful'] += 1
                    success = True
                else:
                    self.stats['failed'] += 1
                    success = False
                
                # Update response time stats
                self.stats['max_response_time'] = max(self.stats['max_response_time'], response_time)
                self.stats['min_response_time'] = min(self.stats['min_response_time'], response_time)
                
                # Calculate rolling average
                total = self.stats['successful'] + self.stats['failed']
                current_avg = self.stats['avg_response_time']
                self.stats['avg_response_time'] = (
                    (current_avg * (total - 1) + response_time) / total
                )
            
            # Store for percentile calculation
            try:
                self.response_times.put_nowait(response_time)
            except queue.Full:
                self.response_times.get()
                self.response_times.put(response_time)
            
            # Write individual request to InfluxDB
            self.write_to_influxdb(
                measurement="http_request",
                fields={
                    "response_time": response_time,
                    "status_code": code,
                    "success": 1 if success else 0
                },
                tags={
                    "endpoint": url,
                    "method": "GET"
                }
            )
            
            if response_time > 2.0:
                logging.warning(f"SLOW: {url} - {response.status_code} - {response_time:.2f}s")
            else:
                logging.debug(f"GOOD {url} - {response.status_code} - {response_time:.2f}s")
            
            return True
            
        except requests.exceptions.Timeout:
            with self.lock:
                self.stats['total_requests'] += 1
                self.stats['failed'] += 1
                self.stats['timeouts'] += 1
            
            self.write_to_influxdb(
                measurement="http_request",
                fields={
                    "response_time": 5.0,
                    "status_code": 0,
                    "success": 0
                },
                tags={
                    "endpoint": url,
                    "method": "GET",
                    "error": "timeout"
                }
            )
            
            logging.error(f"TIMEOUT: {url}")
            return False
            
        except Exception as e:
            with self.lock:
                self.stats['total_requests'] += 1
                self.stats['failed'] += 1
            
            self.write_to_influxdb(
                measurement="http_request",
                fields={
                    "response_time": 0.0,
                    "status_code": 0,
                    "success": 0
                },
                tags={
                    "endpoint": url,
                    "method": "GET",
                    "error": str(type(e).__name__)
                }
            )
            
            logging.error(f"ERROR: {url} - {str(e)}")
            return False
    
    def load(self, requests_per_second=100, duration_seconds=None):
        """Generate load with high concurrency"""
        delay = 1.0 / requests_per_second
        max_workers = min(requests_per_second * 2, 200)  # 2x parallelism
        
        logging.info(f"""
╔═══════════════════════════════════════════════════╗
║                 LOAD TEST STARTED                 ║
╠═══════════════════════════════════════════════════╣
║  Target RPS:        {requests_per_second:>6}                       ║
║  Worker Threads:    {max_workers:>6}                       ║
║  Duration:          {'Infinite' if not duration_seconds else f'{duration_seconds}s':>10}                ║
║  Timeout per req:   5s                            ║
╚═══════════════════════════════════════════════════╝
        """)
        
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            request_count = 0
            
            while True:
                # Check duration
                if duration_seconds and (time.time() - start_time) > duration_seconds:
                    logging.info("Duration reached, finishing pending requests...")
                    break
                
                # Submit request
                url = random.choices(self.endpoints, weights=self.endpoint_weights)[0]
                future = executor.submit(self.make_request, url)
                futures.append(future)
                request_count += 1
                
                # Clean up completed futures periodically
                if len(futures) > 1000:
                    futures = [f for f in futures if not f.done()]
                
                # Rate limiting
                time.sleep(delay)
            
            # Wait for remaining requests
            for future in as_completed(futures):
                future.result()
        
        logging.info("Load test completed!")
    
    def print_stats(self):
        """Print detailed statistics periodically"""
        while True:
            time.sleep(10)  # Print every 10 seconds
            with self.lock:
                runtime = time.time() - self.stats['start_time']
                actual_rps = self.stats['total_requests'] / runtime if runtime > 0 else 0
                success_rate = (self.stats['successful'] / self.stats['total_requests'] * 100) if self.stats['total_requests'] > 0 else 0
                
                # Get percentiles
                times_list = list(self.response_times.queue)
                times_list.sort()
                p50 = float(times_list[len(times_list)//2]) if times_list else 0.0
                p95 = float(times_list[int(len(times_list)*0.95)]) if len(times_list) > 20 else 0.0
                p99 = float(times_list[int(len(times_list)*0.99)]) if len(times_list) > 100 else 0.0
                
                # Write aggregated metrics to InfluxDB
                # Handle min_response_time edge case (infinity if no requests)
                min_time = self.stats['min_response_time'] if self.stats['min_response_time'] != float('inf') else 0.0

                self.write_to_influxdb(
                    measurement="load_test_metrics",
                    fields={
                        "total_requests": self.stats['total_requests'],
                        "successful": self.stats['successful'],
                        "failed": self.stats['failed'],
                        "timeouts": self.stats['timeouts'],
                        "actual_rps": actual_rps,
                        "success_rate": success_rate,
                        "avg_response_time": self.stats['avg_response_time'],
                        "min_response_time": min_time,
                        "max_response_time": self.stats['max_response_time'],
                        "p50_response_time": p50,
                        "p95_response_time": p95,
                        "p99_response_time": p99
                    }
                )
                
                logging.info(f"""
╔════════════════════════════════════════════════════════╗
║               REAL-TIME PERFORMANCE STATS              ║
╠════════════════════════════════════════════════════════╣
║  Runtime:           {runtime:>8.0f}s                          ║
║  Total Requests:    {self.stats['total_requests']:>8}                           ║
║  Successful:        {self.stats['successful']:>8} ({success_rate:>5.1f}%)                ║
║  Failed:            {self.stats['failed']:>8}                           ║
║  Timeouts:          {self.stats['timeouts']:>8}                           ║
╠════════════════════════════════════════════════════════╣
║  Target RPS:        Configured                         ║
║  Actual RPS:        {actual_rps:>8.1f}                           ║
╠════════════════════════════════════════════════════════╣
║  Response Times:                                       ║
║    Average:         {self.stats['avg_response_time']:>7.3f}s                         ║
║    Min:             {self.stats['min_response_time']:>7.3f}s                         ║
║    Max:             {self.stats['max_response_time']:>7.3f}s                         ║
║    P50 (median):    {p50:>7.3f}s                         ║
║    P95:             {p95:>7.3f}s                         ║
║    P99:             {p99:>7.3f}s                         ║
╠════════════════════════════════════════════════════════╣
║  Status Codes:                                         ║
                """)
                
                for code, count in sorted(self.stats['status_codes'].items()):
                    logging.info(f"║    {code}: {count:>8}                                    ║")
                
                logging.info("╚════════════════════════════════════════════════════════╝")
                
                if success_rate < 95:
                    logging.warning("WARNING: Success rate below 95%")
                if actual_rps < (self.stats['total_requests'] / runtime * 0.8):
                    logging.warning("WARNING: Not keeping up with target RPS")
                if self.stats['avg_response_time'] > 2.0:
                    logging.warning("WARNING: Average response time exceeds 2 seconds")

if __name__ == '__main__':
    generator = LoadGenerator()
    
    stats_thread = threading.Thread(target=generator.print_stats, daemon=True)
    stats_thread.start()
    
    generator.load(requests_per_second=1, duration_seconds=None)