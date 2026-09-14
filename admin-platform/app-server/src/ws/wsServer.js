const { WebSocketServer, WebSocket } = require('ws');
const { randomUUID } = require('crypto');

const HEARTBEAT_INTERVAL_MS = 30_000;

function send(ws, data) {
  if (ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(data));
  }
}

function createWsServer(port) {
  const wss = new WebSocketServer({ port });
  const clients = new Map(); // clientId -> ws

  function broadcast(data) {
    const payload = JSON.stringify(data);
    let delivered = 0;
    for (const ws of clients.values()) {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(payload);
        delivered += 1;
      }
    }
    return delivered;
  }

  function handleMessage(clientId, ws, msg) {
    switch (msg.type) {
      case 'ping':
        send(ws, { type: 'pong', at: new Date().toISOString() });
        break;
      case 'chat':
        broadcast({ type: 'chat', from: clientId, payload: msg.payload, at: new Date().toISOString() });
        break;
      default:
        send(ws, { type: 'error', message: `unknown message type: ${msg.type}` });
    }
  }

  wss.on('connection', (ws) => {
    const clientId = randomUUID();
    ws.isAlive = true;
    clients.set(clientId, ws);
    console.log(`[ws] connected ${clientId} (total ${clients.size})`);

    send(ws, { type: 'welcome', clientId });

    ws.on('pong', () => {
      ws.isAlive = true;
    });

    ws.on('message', (raw) => {
      let msg;
      try {
        msg = JSON.parse(raw.toString());
      } catch {
        send(ws, { type: 'error', message: 'invalid JSON' });
        return;
      }
      handleMessage(clientId, ws, msg);
    });

    ws.on('close', () => {
      clients.delete(clientId);
      console.log(`[ws] disconnected ${clientId} (total ${clients.size})`);
    });
  });

  // 응답 없는 연결 정리
  const heartbeat = setInterval(() => {
    for (const [clientId, ws] of clients) {
      if (!ws.isAlive) {
        ws.terminate();
        clients.delete(clientId);
        continue;
      }
      ws.isAlive = false;
      ws.ping();
    }
  }, HEARTBEAT_INTERVAL_MS);

  wss.on('close', () => clearInterval(heartbeat));

  return {
    broadcast,
    getClientCount: () => clients.size,
    close: () =>
      new Promise((resolve) => {
        for (const ws of clients.values()) ws.terminate();
        wss.close(() => resolve());
      }),
  };
}

module.exports = { createWsServer };
