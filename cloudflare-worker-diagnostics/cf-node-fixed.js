import { connect } from 'cloudflare:sockets';

// Replace these two values with your real, private settings.
const UUID = 'REPLACE-WITH-YOUR-UUID';
const WS_PATH = 'REPLACE-WITH-YOUR-SECRET-PATH';
const NODE_NAME = 'Cloudflare-CF';
const BUILD = 'cf-node-diagnostic-20261110-v1';

const encoder = new TextEncoder();
const decoder = new TextDecoder();
const path = '/' + WS_PATH.replace(/^\/+/, '');
const validUUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(UUID);
const validPath = /^[A-Za-z0-9_/-]{8,128}$/.test(WS_PATH) && !WS_PATH.startsWith('/');

function getUuidBytes() {
  const hex = UUID.replace(/-/g, '');
  return Uint8Array.from(hex.match(/.{2}/g), x => parseInt(x, 16));
}

function vlessLink(host) {
  const p = encodeURIComponent(path);
  return `vless://${UUID}@${host}:443?encryption=none&security=tls&type=ws&host=${host}&path=${p}&sni=${host}#${encodeURIComponent(NODE_NAME)}`;
}

// Return null if the header has not arrived in full yet.
function parseHeader(buf, uuidBytes) {
  if (buf.length < 18) return null;
  const version = buf[0];
  if (version !== 0) return { error: 'unsupported vless version' };
  for (let i = 0; i < 16; i++) {
    if (buf[1 + i] !== uuidBytes[i]) return { error: 'bad uuid' };
  }

  const commandIndex = 18 + buf[17];
  if (buf.length < commandIndex + 4) return null;
  const cmd = buf[commandIndex];
  const port = (buf[commandIndex + 1] << 8) | buf[commandIndex + 2];
  const addrType = buf[commandIndex + 3];
  if (port === 0) return { error: 'bad port' };

  let addr;
  let end;
  const start = commandIndex + 4;
  if (addrType === 1) {
    if (buf.length < start + 4) return null;
    addr = Array.from(buf.subarray(start, start + 4)).join('.');
    end = start + 4;
  } else if (addrType === 2) {
    if (buf.length < start + 1) return null;
    const len = buf[start];
    if (!len) return { error: 'empty domain' };
    if (buf.length < start + 1 + len) return null;
    addr = decoder.decode(buf.subarray(start + 1, start + 1 + len));
    end = start + 1 + len;
  } else if (addrType === 3) {
    if (buf.length < start + 16) return null;
    const words = [];
    for (let i = 0; i < 16; i += 2) {
      words.push(((buf[start + i] << 8) | buf[start + i + 1]).toString(16));
    }
    addr = words.join(':');
    end = start + 16;
  } else {
    return { error: 'bad address type' };
  }

  return { version, cmd, port, addr, payload: buf.subarray(end) };
}

async function handleVless() {
  const pair = new WebSocketPair();
  const client = pair[0];
  const server = pair[1];
  server.accept();
  server.binaryType = 'arraybuffer';

  const uuidBytes = getUuidBytes();
  let header = new Uint8Array(0);
  let established = false;
  let stopped = false;
  let socket = null;
  let writer = null;
  let pending = Promise.resolve();

  function closeBoth(code = 1000, reason = '') {
    if (stopped) return;
    stopped = true;
    try { socket?.close(); } catch {}
    try { server.close(code, reason); } catch {}
  }

  async function pumpRemote() {
    const reader = socket.readable.getReader();
    try {
      while (!stopped) {
        const { done, value } = await reader.read();
        if (done) break;
        if (value && value.byteLength) server.send(value);
      }
    } catch (e) {
      console.error('tcp to websocket failed:', e);
    } finally {
      try { reader.releaseLock(); } catch {}
      closeBoth();
    }
  }

  async function onMessage(event) {
    if (stopped) return;
    let data;
    if (event.data instanceof ArrayBuffer) {
      data = new Uint8Array(event.data);
    } else if (event.data instanceof Blob) {
      data = new Uint8Array(await event.data.arrayBuffer());
    } else if (typeof event.data === 'string') {
      data = encoder.encode(event.data);
    } else {
      throw new Error('unexpected WebSocket frame type');
    }

    if (!established) {
      const combined = new Uint8Array(header.length + data.length);
      combined.set(header);
      combined.set(data, header.length);
      const h = parseHeader(combined, uuidBytes);
      if (h === null) {
        if (combined.length > 8192) throw new Error('oversized incomplete header');
        header = combined;
        return;
      }
      if (h.error) throw new Error(h.error);
      if (h.cmd !== 1) throw new Error('only TCP supported');

      established = true;
      header = new Uint8Array(0);
      socket = connect({ hostname: h.addr, port: h.port });
      writer = socket.writable.getWriter();
      // VLESS response: version + zero additional-info length.
      server.send(new Uint8Array([h.version, 0]));
      void pumpRemote();
      if (h.payload.byteLength) await writer.write(h.payload);
    } else {
      await writer.write(data);
    }
  }

  server.addEventListener('close', () => closeBoth());
  server.addEventListener('error', () => closeBoth(1011, 'websocket error'));
  server.addEventListener('message', event => {
    // Preserve message order even when writes await backpressure.
    pending = pending.then(() => onMessage(event)).catch(e => {
      console.error('VLESS connection error:', e);
      closeBoth(1002, 'connection failed');
    });
  });

  return new Response(null, { status: 101, webSocket: client });
}

export default {
  async fetch(request) {
    try {
      const url = new URL(request.url);
      const headers = { 'X-Worker-Build': BUILD, 'Cache-Control': 'no-store' };
      console.log('CF_NODE_REQUEST', { build: BUILD, path: url.pathname, colo: request.cf?.colo || 'unknown' });

      if (url.pathname === '/') {
        return new Response(`<!doctype html><meta charset="utf-8"><title>${NODE_NAME}</title><h1>${NODE_NAME} is running</h1><p>Build: ${BUILD}</p>`, {
          headers: { ...headers, 'Content-Type': 'text/html; charset=utf-8' }
        });
      }
      if (url.pathname === '/healthz') {
        return new Response('ok ' + BUILD + '\n', {
          headers: { ...headers, 'Content-Type': 'text/plain; charset=utf-8' }
        });
      }
      if (!validUUID || !validPath) {
        return new Response('Invalid UUID or WS_PATH configuration\n', { status: 503, headers });
      }
      if (url.pathname === '/vless') {
        return new Response(vlessLink(url.hostname) + '\n', {
          headers: { ...headers, 'Content-Type': 'text/plain; charset=utf-8' }
        });
      }
      if (url.pathname === '/sub') {
        // The vless:// URI is ASCII because its non-ASCII components are URL encoded.
        return new Response(btoa(vlessLink(url.hostname) + '\n') + '\n', {
          headers: { ...headers, 'Content-Type': 'text/plain; charset=utf-8' }
        });
      }
      if (url.pathname === path) {
        const upgrade = (request.headers.get('Upgrade') || '').toLowerCase();
        if (upgrade === 'websocket') return handleVless();
        return new Response('Expected WebSocket upgrade\n', { status: 400, headers });
      }
      return new Response('Not found\n', { status: 404, headers });
    } catch (e) {
      console.error('CF_NODE_FETCH_FAILURE:', e);
      return new Response('Internal Worker error\n', { status: 500 });
    }
  }
};
