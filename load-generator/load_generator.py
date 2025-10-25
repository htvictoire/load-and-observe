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
    format='%(levelname)s - %(message)s'
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
        try:
            start_time = time.time()
            response = requests.get(url, timeout=5)
            response_time = time.time() - start_time
            
            with self.lock:
                self.stats['total_requests'] += 1
                
                code = response.status_code
                self.stats['status_codes'][code] = self.stats['status_codes'].get(code, 0) + 1
                
                if response.status_code == 200:
                    self.stats['successful'] += 1
                    success = True
                else:
                    self.stats['failed'] += 1
                    success = False
                
                self.stats['max_response_time'] = max(self.stats['max_response_time'], response_time)
                self.stats['min_response_time'] = min(self.stats['min_response_time'], response_time)
                
                total = self.stats['successful'] + self.stats['failed']
                current_avg = self.stats['avg_response_time']
                self.stats['avg_response_time'] = (
                    (current_avg * (total - 1) + response_time) / total
                )
            
            try:
                self.response_times.put_nowait(response_time)
            except queue.Full:
                self.response_times.get()
                self.response_times.put(response_time)
            
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
        delay = 1.0 / requests_per_second
        max_workers = min(requests_per_second * 2, 200)
        
        duration_display = 'Infinite' if not duration_seconds else f'{duration_seconds}s'
        
        logging.info("=" * 68)
        logging.info("                        LOAD TEST STARTED                        ")
        logging.info("=" * 68)
        logging.info(f"  Target RPS         : {requests_per_second:>10}")
        logging.info(f"  Worker Threads     : {max_workers:>10}")
        logging.info(f"  Duration           : {duration_display:>10}")
        logging.info(f"  Timeout per req    : {'5s':>10}")
        logging.info("=" * 68)
        
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = []
            request_count = 0
            
            while True:
                if duration_seconds and (time.time() - start_time) > duration_seconds:
                    logging.info("Duration reached, finishing pending requests...")
                    break
                
                url = random.choices(self.endpoints, weights=self.endpoint_weights)[0]
                future = executor.submit(self.make_request, url)
                futures.append(future)
                request_count += 1
                
                if len(futures) > 1000:
                    futures = [f for f in futures if not f.done()]
                
                time.sleep(delay)
            
            for future in as_completed(futures):
                future.result()
        
        logging.info("Load test completed!")
    
    def print_stats(self):
        while True:
            time.sleep(10)
            with self.lock:
                runtime = time.time() - self.stats['start_time']
                actual_rps = self.stats['total_requests'] / runtime if runtime > 0 else 0
                success_rate = (self.stats['successful'] / self.stats['total_requests'] * 100) if self.stats['total_requests'] > 0 else 0
                
                times_list = list(self.response_times.queue)
                times_list.sort()
                p50 = float(times_list[len(times_list)//2]) if times_list else 0.0
                p95 = float(times_list[int(len(times_list)*0.95)]) if len(times_list) > 20 else 0.0
                p99 = float(times_list[int(len(times_list)*0.99)]) if len(times_list) > 100 else 0.0
                
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
                
                logging.info("")
                logging.info("")
                logging.info("")
                logging.info("")
                logging.info("")
                logging.info("=" * 68)
                logging.info("                  REAL-TIME PERFORMANCE STATS                  ")
                logging.info("=" * 68)
                logging.info(f"  Runtime            : {runtime:>10.0f}s")
                logging.info(f"  Total Requests     : {self.stats['total_requests']:>10}")
                logging.info(f"  Successful         : {self.stats['successful']:>10}")
                logging.info(f"  Success Rate       : {success_rate:>9.1f}%")
                logging.info(f"  Failed             : {self.stats['failed']:>10}")
                logging.info(f"  Timeouts           : {self.stats['timeouts']:>10}")
                logging.info("=" * 68)
                logging.info(f"  Target RPS         : {'Configured':>10}")
                logging.info(f"  Actual RPS         : {actual_rps:>10.1f}")
                logging.info("=" * 68)
                logging.info("  Response Times")
                logging.info(f"    Average          : {self.stats['avg_response_time']:>10.3f}s")
                logging.info(f"    Min              : {min_time:>10.3f}s")
                logging.info(f"    Max              : {self.stats['max_response_time']:>10.3f}s")
                logging.info(f"    P50 (median)     : {p50:>10.3f}s")
                logging.info(f"    P95              : {p95:>10.3f}s")
                logging.info(f"    P99              : {p99:>10.3f}s")
                logging.info("=" * 68)
                logging.info("  Status Codes")
                
                for code, count in sorted(self.stats['status_codes'].items()):
                    logging.info(f"    {code}              : {count:>10}")
                
                logging.info("=" * 68)
                logging.info("")
                
                if success_rate < 95:
                    logging.warning("=" * 68)
                    logging.warning("  WARNING: Success rate below 95%")
                    logging.warning("=" * 68)
                    logging.warning("")
                if actual_rps < (self.stats['total_requests'] / runtime * 0.8):
                    logging.warning("=" * 68)
                    logging.warning("  WARNING: Not keeping up with target RPS")
                    logging.warning("=" * 68)
                    logging.warning("")
                if self.stats['avg_response_time'] > 2.0:
                    logging.warning("=" * 68)
                    logging.warning("  WARNING: Average response time exceeds 2 seconds")
                    logging.warning("=" * 68)
                    logging.warning("")

if __name__ == '__main__':
    generator = LoadGenerator()
    
    stats_thread = threading.Thread(target=generator.print_stats, daemon=True)
    stats_thread.start()
    
    generator.load(requests_per_second=1, duration_seconds=None)