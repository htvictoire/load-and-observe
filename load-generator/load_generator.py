import requests
import time
import random
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import queue

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
        
        # Weighted probability - hit stress endpoints more
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
                else:
                    self.stats['failed'] += 1
                
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
            
            if response_time > 2.0:
                logging.warning(f"SLOW: {url} - {response.status_code} - {response_time:.2f}s")
            else:
                logging.debug(f"GOOD {url} - {response.status_code} - {response_time:.2f}s")
            
            return True
            
        except Exception as e:
            logging.error(f"ERROR: {url} - {str(e)}")
            return False
    
    def load(self, requests_per_second=100, duration_seconds=None):
        """Generate aggressive load with high concurrency"""
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
            time.sleep(10)  # Print every 10 seconds during heavy load
            
            with self.lock:
                runtime = time.time() - self.stats['start_time']
                actual_rps = self.stats['total_requests'] / runtime if runtime > 0 else 0
                success_rate = (self.stats['successful'] / self.stats['total_requests'] * 100) if self.stats['total_requests'] > 0 else 0
                
                # Get percentiles
                times_list = list(self.response_times.queue)
                times_list.sort()
                p50 = times_list[len(times_list)//2] if times_list else 0
                p95 = times_list[int(len(times_list)*0.95)] if len(times_list) > 20 else 0
                p99 = times_list[int(len(times_list)*0.99)] if len(times_list) > 100 else 0
                
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
                
                # Warning indicators
                if success_rate < 95:
                    logging.warning("WARNING: Success rate below 95%! VPS is struggling!")
                if actual_rps < (self.stats['total_requests'] / runtime * 0.8):
                    logging.warning("WARNING: Not keeping up with target RPS!")
                if self.stats['avg_response_time'] > 2.0:
                    logging.warning("WARNING: Average response time > 2s!")

if __name__ == '__main__':
    generator = LoadGenerator()
    
    # Start stats printer in background
    stats_thread = threading.Thread(target=generator.print_stats, daemon=True)
    stats_thread.start()
    
    # CHOOSE YOUR LOAD LEVEL:
    
    # Light test (warm up)
    # generator.load(requests_per_second=50, duration_seconds=60)
    
    # Moderate traffic (100 req/sec) - Should push VPS
    generator.load(requests_per_second=100, duration_seconds=None)
    
    # Heavy traffic (150 req/sec) - Should really struggle
    # generator.load(requests_per_second=150, duration_seconds=None)
    
    # Stress test (200 req/sec) - Likely to fail
    # generator.load(requests_per_second=200, duration_seconds=None)
    
    # EXTREME (300+ req/sec) - Will definitely crash
    # generator.load(requests_per_second=300, duration_seconds=300)