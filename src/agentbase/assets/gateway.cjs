'use strict';

// First-party, optional sidecar. No dependencies, environment credentials or logs.
const http = require('node:http');
const https = require('node:https');
const crypto = require('node:crypto');

const SPEC = require('./gateway-policy.json');
const TARGETS = SPEC.targets;
const FIELDS = SPEC.fields;

// An intentionally narrow text/client-tool subset. Future provider features must
// be reviewed explicitly rather than inheriting the gateway's credential.
const REQUEST_FIELDS = {
  codex: ['model', 'input', 'instructions', 'tools', 'tool_choice', 'parallel_tool_calls',
    'reasoning', 'store', 'stream', 'include', 'text', 'max_output_tokens',
    'metadata', 'temperature', 'top_p', 'truncation', 'prompt_cache_key', 'client_metadata'],
  claude: ['model', 'messages', 'system', 'tools', 'tool_choice', 'max_tokens',
    'stop_sequences', 'stream', 'temperature', 'top_p', 'top_k', 'metadata',
    'thinking', 'output_config'],
};

function onlyFields(value, allowed) {
  if (Object.keys(value).some(key => !allowed.includes(key))) throw new Error('unreviewed request field');
}

function clientTool(tool, provider, nested = false) {
  if (!tool || typeof tool !== 'object' || Array.isArray(tool)) throw new Error('invalid tool');
  if (provider === 'claude') {
    if (![undefined, 'custom'].includes(tool.type)) throw new Error('hosted tool refused');
    onlyFields(tool, ['type', 'name', 'description', 'input_schema', 'cache_control', 'strict']);
  } else if (tool.type === 'namespace' && !nested) {
    onlyFields(tool, ['type', 'name', 'description', 'tools']);
    if (typeof tool.name !== 'string' || !/^[A-Za-z0-9_-]{1,128}$/.test(tool.name) ||
        !Array.isArray(tool.tools) || tool.tools.length < 1) throw new Error('tool namespace refused');
    for (const member of tool.tools) clientTool(member, provider, true);
  } else if (tool.type === 'function') {
    onlyFields(tool, ['type', 'name', 'description', 'parameters', 'strict']);
  } else if (tool.type === 'custom') {
    onlyFields(tool, ['type', 'name', 'description', 'format']);
  } else throw new Error('hosted tool refused');
}

class ProtocolError extends Error {
  constructor(status) { super('gateway request refused'); this.status = status; }
}

function validatePolicy(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value) ||
      Object.keys(value).sort().join() !== [...FIELDS].sort().join() || value.schema_version !== 1 ||
      !Object.hasOwn(TARGETS, value.provider) || typeof value.model !== 'string' ||
      !/^[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}$/.test(value.model)) throw new Error('invalid gateway policy');
  for (const [key, [low, high]] of Object.entries(SPEC.limits)) {
    if (!Number.isSafeInteger(value[key]) || value[key] < low || value[key] > high)
      throw new Error('invalid gateway limit');
  }
  if (value.timeout_seconds > value.lifetime_seconds) throw new Error('invalid gateway deadline');
  return Object.freeze({...value});
}

function sanitizeRequest(body, policy) {
  if (!body || typeof body !== 'object' || Array.isArray(body) || body.model !== policy.model)
    throw new Error('model or request schema refused');
  for (const key of ['background', 'conversation', 'previous_response_id', 'prompt']) {
    if (Object.hasOwn(body, key) && body[key] !== false && body[key] !== null)
      throw new Error('detached or stored context refused');
    delete body[key];
  }
  for (const key of ['service_tier', 'speed', 'fast_mode']) {
    if (Object.hasOwn(body, key)) throw new Error('non-default service tier refused');
  }
  onlyFields(body, REQUEST_FIELDS[policy.provider]);
  if (Object.hasOwn(body, 'stream') && typeof body.stream !== 'boolean') throw new Error('invalid stream flag');
  if (body.tools !== undefined) {
    if (!Array.isArray(body.tools) || body.tools.length > 64) throw new Error('tool list refused');
    let totalTools = body.tools.length;
    for (const tool of body.tools) {
      clientTool(tool, policy.provider);
      if (policy.provider === 'codex' && tool.type === 'namespace') {
        if ((totalTools += tool.tools.length) > 64) throw new Error('tool namespace refused');
      }
    }
  }
  let count = 0;
  const pending = [body];
  while (pending.length) {
    const item = pending.pop();
    if (++count > 20000) throw new Error('request nesting limit');
    if (item && typeof item === 'object') {
      if (['input_image', 'input_file', 'image', 'document', 'input_audio', 'item_reference',
          'mcp_call', 'mcp_approval_response', 'mcp_tool_use', 'mcp_tool_result', 'server_tool_use'].includes(item.type))
        throw new Error('remote or non-text input refused');
      for (const [key, value] of Object.entries(item)) {
        if (['file_id', 'file_url', 'image_url'].includes(key)) throw new Error('remote file input refused');
        pending.push(value);
      }
    }
  }
  const key = policy.provider === 'codex' ? 'max_output_tokens' : 'max_tokens';
  const requested = body[key];
  if (requested !== undefined && (!Number.isSafeInteger(requested) || requested < 1)) throw new Error('invalid output limit');
  body[key] = Math.min(requested ?? policy.max_output_tokens, policy.max_output_tokens);
  if (policy.provider === 'codex') body.store = false;
  return Buffer.from(JSON.stringify(body));
}

function equalToken(actual, expected) {
  return typeof actual === 'string' && Buffer.byteLength(actual) === Buffer.byteLength(expected) &&
    crypto.timingSafeEqual(Buffer.from(actual), Buffer.from(expected));
}

function authenticated(req, capability) {
  let seen = 0;
  for (let i = 0; i < req.rawHeaders.length; i += 2) {
    const name = req.rawHeaders[i].toLowerCase();
    if (name !== 'authorization' && name !== 'x-api-key') continue;
    ++seen;
    const expected = name === 'authorization' ? 'Bearer ' + capability : capability;
    if (!equalToken(req.rawHeaders[i + 1], expected)) return false;
  }
  // At most one of each header; duplicate auth headers fail closed.
  const names = req.rawHeaders.filter((_, i) => i % 2 === 0).map(n => n.toLowerCase());
  return seen > 0 && names.filter(n => n === 'authorization').length <= 1 && names.filter(n => n === 'x-api-key').length <= 1;
}

function readBody(req, limit) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    req.on('data', chunk => {
      size += chunk.length;
      if (size > limit) { req.pause(); reject(new ProtocolError(413)); }
      else chunks.push(chunk);
    });
    req.on('end', () => resolve(Buffer.concat(chunks)));
    req.on('error', () => reject(new ProtocolError(400)));
    req.on('aborted', () => reject(new ProtocolError(400)));
  });
}

function officialTransport(policy, bytes, credential, signal) {
  const target = TARGETS[policy.provider];
  const headers = {'content-type': 'application/json', 'content-length': String(bytes.length)};
  if (policy.provider === 'codex') headers.authorization = 'Bearer ' + credential;
  else { headers['x-api-key'] = credential; headers['anthropic-version'] = '2023-06-01'; }
  return new Promise((resolve, reject) => {
    const request = https.request({hostname: target.hostname, port: 443, path: target.path,
      method: 'POST', headers, signal}, response => {
      const chunks = [];
      let size = 0;
      response.on('data', chunk => {
        size += chunk.length;
        if (size > policy.max_response_bytes) request.destroy(new Error('response byte limit'));
        else chunks.push(chunk);
      });
      response.on('end', () => resolve({status: response.statusCode,
        type: response.headers['content-type'] || '', body: Buffer.concat(chunks)}));
      response.on('error', () => reject(new Error('upstream response failed')));
    });
    request.on('error', () => reject(new Error('upstream transport failed')));
    request.end(bytes);
  });
}

function createGateway(configuration, credential, capability, transport = officialTransport) {
  if (Number(process.versions.node.split('.')[0]) < 20) throw new Error('Node 20+ required');
  const policy = validatePolicy(configuration);
  if (typeof credential !== 'string' || !/^[\x21-\x7e]{16,4096}$/.test(credential) ||
      typeof capability !== 'string' || !/^[A-Za-z0-9_-]{32,256}$/.test(capability) || credential === capability)
    throw new Error('invalid gateway bootstrap secret');
  const metrics = {attempted_requests: 0, successful_requests: 0, rejected_requests: 0,
    upstream_failures: 0, bytes_sent: 0, bytes_received: 0};
  const controllers = new Set();
  let active = false, expired = false;
  const reply = (res, status, value) => {
    if (!res.destroyed && !res.writableEnded) {
      res.writeHead(status, {'content-type': 'application/json', 'connection': 'close'});
      res.end(JSON.stringify(value));
    }
  };
  const server = http.createServer({maxHeaderSize: 8192}, async (req, res) => {
    const refuse = (status, error) => { ++metrics.rejected_requests; reply(res, status, {error}); };
    if (expired) return refuse(503, 'gateway-expired');
    if (!authenticated(req, capability)) return refuse(401, 'gateway-authentication-required');
    if (req.method === 'GET' && req.url === '/health') return reply(res, 200, {ready: true});
    if (req.method === 'GET' && req.url === '/metrics') return reply(res, 200, {...metrics});
    if (req.method !== 'POST' || !TARGETS[policy.provider].paths.includes(req.url)) return refuse(404, 'route-refused');
    if (active || metrics.attempted_requests >= policy.max_requests) return refuse(429, 'request-budget-or-concurrency-limit');
    if (!/^application\/json(?:\s*;.*)?$/i.test(req.headers['content-type'] || '') ||
        ![undefined, 'identity'].includes(req.headers['content-encoding'])) return refuse(415, 'encoding-refused');
    active = true;
    let attempted = false;
    const controller = new AbortController();
    controllers.add(controller);
    const timer = setTimeout(() => controller.abort(), policy.timeout_seconds * 1000);
    const disconnected = () => { if (!res.writableEnded) controller.abort(); };
    res.on('close', disconnected);
    try {
      const raw = await Promise.race([readBody(req, policy.max_request_bytes), new Promise((_, reject) => {
        controller.signal.addEventListener('abort', () => reject(new Error('deadline')), {once: true});
      })]);
      let bytes;
      try { bytes = sanitizeRequest(JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(raw)), policy); }
      catch { return refuse(422, 'request-schema-refused'); }
      if (bytes.length > policy.max_request_bytes) return refuse(413, 'request-byte-limit');
      if (controller.signal.aborted) return refuse(408, 'request-deadline');
      ++metrics.attempted_requests;  // Attempted calls never refund budget on failure.
      attempted = true;
      metrics.bytes_sent += bytes.length;
      const upstream = await Promise.race([transport(policy, bytes, credential, controller.signal), new Promise((_, reject) => {
        controller.signal.addEventListener('abort', () => reject(new Error('deadline')), {once: true});
      })]);
      if (!upstream || upstream.status !== 200 || !Buffer.isBuffer(upstream.body) ||
          upstream.body.length > policy.max_response_bytes || !/^(application\/json|text\/event-stream)(?:\s*;.*)?$/i.test(upstream.type || ''))
        throw new Error('upstream response refused');
      // Buffer bounded SSE/JSON before forwarding, so a secret split across chunks
      // cannot bypass the literal redaction. Redirects/errors/headers are not relayed.
      const content = new TextDecoder('utf-8', {fatal: true}).decode(upstream.body).split(credential).join('[redacted]');
      ++metrics.successful_requests;
      metrics.bytes_received += upstream.body.length;
      if (!res.destroyed) {
        res.writeHead(200, {'content-type': upstream.type, 'connection': 'close'});
        res.end(content);
      }
    } catch (error) {
      if (attempted) ++metrics.upstream_failures;
      else ++metrics.rejected_requests;
      const status = error instanceof ProtocolError ? error.status : (controller.signal.aborted ? (attempted ? 504 : 408) : 502);
      reply(res, status, {error: 'bounded-request-failed'});
    } finally {
      clearTimeout(timer);
      controllers.delete(controller);
      res.removeListener('close', disconnected);
      active = false;
    }
  });
  server.maxConnections = 4;
  server.maxRequestsPerSocket = 1;
  server.headersTimeout = 5000;
  server.requestTimeout = Math.min(policy.timeout_seconds * 1000, 5000);
  server.on('connect', (_, socket) => socket.destroy());
  server.on('upgrade', (_, socket) => socket.destroy());
  server.on('clientError', (_, socket) => { socket.end('HTTP/1.1 400 Bad Request\r\nConnection: close\r\n\r\n'); });
  const stop = () => {
    if (expired) return;
    expired = true;
    for (const controller of controllers) controller.abort();
    server.close();
    server.closeAllConnections();
  };
  const lifetime = setTimeout(stop, policy.lifetime_seconds * 1000);
  lifetime.unref();
  server.on('close', () => clearTimeout(lifetime));
  return {server, stop, metrics, policy};
}

if (require.main === module) {
  let bootstrap = '', started = false;
  process.stdin.setEncoding('utf8');
  process.stdin.on('data', chunk => {
    if (started) return;
    bootstrap += chunk;
    if (Buffer.byteLength(bootstrap) > 16384) process.exit(2);
    const end = bootstrap.indexOf('\n');
    if (end < 0) return;
    try {
      const value = JSON.parse(bootstrap.slice(0, end));
      bootstrap = '';
      const gateway = createGateway(value.policy, value.credential, value.capability);
      started = true;
      gateway.server.on('error', () => { process.stderr.write('Gateway listen failed\n'); process.exit(2); });
      gateway.server.on('close', () => process.stdin.destroy());
      gateway.server.listen(8787, '0.0.0.0', () => process.stdout.write('{"ready":true}\n'));
      process.stdin.on('end', gateway.stop);
      process.on('SIGTERM', gateway.stop);
      process.on('SIGINT', gateway.stop);
    } catch { process.stderr.write('Gateway bootstrap refused\n'); process.exit(2); }
  });
  process.stdin.on('end', () => { if (!started) process.exit(2); });
}

module.exports = {validatePolicy, sanitizeRequest, createGateway};
