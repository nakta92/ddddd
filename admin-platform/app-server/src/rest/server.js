const express = require('express');
const cors = require('cors');

function createRestServer(wsHub) {
  const app = express();
  const startedAt = Date.now();

  app.use(cors());
  app.use(express.json());

  app.get('/health', (req, res) => {
    res.json({ status: 'ok', service: 'app-server' });
  });

  app.get('/api/stats', (req, res) => {
    res.json({
      wsClients: wsHub.getClientCount(),
      uptimeSec: Math.floor((Date.now() - startedAt) / 1000),
    });
  });

  app.post('/api/broadcast', (req, res) => {
    const { message } = req.body ?? {};
    if (!message || typeof message !== 'string') {
      return res.status(400).json({ error: 'message is required' });
    }
    const delivered = wsHub.broadcast({ type: 'notice', message, at: new Date().toISOString() });
    return res.json({ delivered });
  });

  app.use((req, res) => {
    res.status(404).json({ error: 'Not Found' });
  });

  app.use((err, req, res, next) => {
    console.error('[rest] error', err);
    res.status(500).json({ error: 'Internal Server Error' });
  });

  return app;
}

module.exports = { createRestServer };
