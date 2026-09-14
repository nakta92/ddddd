const config = require('./config');
const { createWsServer } = require('./ws/wsServer');
const { createRestServer } = require('./rest/server');

const wsHub = createWsServer(config.wsPort);
console.log(`[ws] listening on ws://0.0.0.0:${config.wsPort}`);

const app = createRestServer(wsHub);
const restServer = app.listen(config.restPort, () => {
  console.log(`[rest] listening on http://0.0.0.0:${config.restPort}`);
});

async function shutdown(signal) {
  console.log(`${signal} received, shutting down`);
  restServer.close();
  await wsHub.close();
  process.exit(0);
}

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
