const express = require('express');
const { Pool } = require('pg');
const redis = require('redis');

const app = express();
const port = 3000;

// Database connection
const pool = new Pool({
  connectionString: process.env.DATABASE_URL
});

// Redis connection
const redisClient = redis.createClient({
  url: process.env.REDIS_URL
});
redisClient.connect().catch(console.error);

app.get('/', (req, res) => {
  res.json({ 
    message: 'Node.js API is running!',
    timestamp: Date.now()
  });
});

app.get('/health', async (req, res) => {
  const health = {
    status: 'healthy',
    service: 'nodejs',
    timestamp: Date.now()
  };

  // Test database
  try {
    await pool.query('SELECT NOW()');
    health.database = 'connected';
  } catch (error) {
    health.database = `error: ${error.message}`;
  }

  // Test Redis
  try {
    await redisClient.ping();
    health.redis = 'connected';
  } catch (error) {
    health.redis = `error: ${error.message}`;
  }

  res.json(health);
});

app.get('/stress', (req, res) => {
  // Simulate CPU work
  let result = 0;
  for (let i = 0; i < 10000000; i++) {
    result += Math.sqrt(i);
  }
  res.json({ result, message: 'Stress test completed' });
});

app.listen(port, '0.0.0.0', () => {
  console.log(`Node.js app listening on port ${port}`);
});
