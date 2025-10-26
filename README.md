## License
This project is licensed under the Creative Commons Attribution–NonCommercial 4.0 International License (CC BY-NC 4.0).

# Heavy Stack Test

A comprehensive microservices application demonstrating load balancing, monitoring, and performance testing.

## Architecture

This project consists of multiple services working together:

- **FastAPI Backend**: Python-based API service with health checks and stress testing endpoints
- **Node.js Service**: Express-based service providing similar endpoints for comparison
- **Nginx**: Reverse proxy with load balancing between FastAPI and Node.js services
- **PostgreSQL**: Relational database for persistent storage
- **Redis**: In-memory cache for fast data access
- **Prometheus**: Metrics collection and monitoring
- **Grafana**: Visualization and dashboards
- **Load Generator**: Python-based tool for stress testing with configurable RPS

## Quick Start

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop all services
docker-compose down
```

## Service Endpoints

- **Nginx Proxy**: http://localhost:80
- **Grafana**: http://localhost:3001 (admin/admin)
- **Prometheus**: http://localhost:9090

## Load Testing

The load generator supports multiple intensity levels:

```python
# Edit load-generator/load_generator.py to choose your test:
generator.load(requests_per_second=100, duration_seconds=None)
```

## Monitoring

Access Grafana at http://localhost:3001 to view real-time metrics including:
- Request rates and response times
- Resource utilization (CPU, Memory)
- Container health status
