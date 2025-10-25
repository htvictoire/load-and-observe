// OpenTelemetry must be initialized BEFORE any other imports
const { NodeSDK } = require('@opentelemetry/sdk-node');
const { OTLPTraceExporter } = require('@opentelemetry/exporter-trace-otlp-http');
const { getNodeAutoInstrumentations } = require('@opentelemetry/auto-instrumentations-node');
const { trace } = require('@opentelemetry/api');

const sdk = new NodeSDK({
  traceExporter: new OTLPTraceExporter({
    url: `${process.env.OTEL_EXPORTER_OTLP_ENDPOINT || 'http://tempo:4318'}/v1/traces`,
  }),
  instrumentations: [getNodeAutoInstrumentations()],
});

// start SDK safely (handle implementations that don't return a Promise)
(async () => {
  try {
    if (typeof sdk.start === 'function') {
      await sdk.start();
      console.log('OpenTelemetry SDK started');
    }
  } catch (err) {
    console.error('Failed to start OpenTelemetry SDK', err);
  }
})();

process.on('SIGTERM', async () => {
  try {
    if (typeof sdk.shutdown === 'function') {
      await sdk.shutdown();
      console.log('Tracing terminated');
    }
  } catch (error) {
    console.error('Error terminating tracing', error);
  } finally {
    process.exit(0);
  }
});

process.on('SIGINT', async () => {
  try {
    if (typeof sdk.shutdown === 'function') {
      await sdk.shutdown();
      console.log('Tracing terminated (SIGINT)');
    }
  } catch (error) {
    console.error('Error terminating tracing', error);
  } finally {
    process.exit(0);
  }
});

const express = require('express');
const { Pool } = require('pg');
const redis = require('redis');

const app = express();
const port = 3000;

const pool = new Pool({
  connectionString: process.env.DATABASE_URL
});

const redisClient = redis.createClient({
  url: process.env.REDIS_URL
});
redisClient.connect().catch(console.error);

app.get('/', (req, res) => {
  const span = trace.getActiveSpan();
  const traceId = span ? span.spanContext().traceId : null;

  res.json({
    message: 'Node.js API is running!',
    timestamp: Date.now(),
    trace_id: traceId
  });
});

app.get('/health', async (req, res) => {
  const health = {
    status: 'healthy',
    service: 'nodejs',
    timestamp: Date.now()
  };

  try {
    await pool.query('SELECT NOW()');
    health.database = 'connected';
  } catch (error) {
    health.database = `error: ${error.message}`;
  }

  try {
    await redisClient.ping();
    health.redis = 'connected';
  } catch (error) {
    health.redis = `error: ${error.message}`;
  }

  res.json(health);
});

app.get('/stress', (req, res) => {
  const span = trace.getActiveSpan();
  const traceId = span ? span.spanContext().traceId : null;

  const tracer = trace.getTracer('nodejs-app');
  const computeSpan = tracer.startSpan('heavy_computation');

  let result = 0;
  for (let i = 0; i < 10000000; i++) {
    result += Math.sqrt(i);
  }

  computeSpan.end();

  res.json({
    result,
    message: 'Stress test completed',
    trace_id: traceId
  });
});

app.listen(port, '0.0.0.0', () => {
  console.log(`Node.js app listening on port ${port}`);
});