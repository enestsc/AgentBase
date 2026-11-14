'use strict';
// All credentials, models, responses and transports below are synthetic fixtures.
const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const net = require('node:net');
const https = require('node:https');
const {EventEmitter} = require('node:events');
const {Readable} = require('node:stream');
const {createGateway, validatePolicy, sanitizeRequest} = require('../src/agentbase/assets/gateway.cjs');

const SECRET = 'synthetic-provider-secret-not-a-real-key';
const CAP = 'synthetic_gateway_capability_0123456789';
const POLICY = {schema_version: 1, provider: 'codex', model: 'fixture-model', max_requests: 3,
  max_output_tokens: 128, max_request_bytes: 2048, max_response_bytes: 2048,
  timeout_seconds: 1, lifetime_seconds: 10};
const BODY = {model: 'fixture-model', input: 'Synthetic test input'};
const response = (text = 'fixture') => ({status: 200, type: 'application/json', body: Buffer.from(JSON.stringify({text}))});

test('client tool namespaces never permit hosted or nested namespaces', () => {
  const local = {type: 'namespace', name: 'functions', tools: [{type: 'function', name: 'fixture'}, {type: 'custom', name: 'literal'}]};
  assert.equal(JSON.parse(sanitizeRequest({...BODY, tools: [local]}, POLICY)).tools[0].name, 'functions');
  for (const bad of [{...local, tools: [{type: 'web_search'}]}, {...local, tools: [local]}, {...local, tools: []},
      {...local, tools: Array.from({length: 64}, () => ({type: 'function'}))}, {...local, name: '../bad'}])
    assert.throws(() => sanitizeRequest({...BODY, tools: [bad]}, POLICY));
  assert.throws(() => sanitizeRequest({...BODY, tools: [local]}, {...POLICY, provider: 'claude'}));
});

test('only the literal Claude beta query maps to the same fixed Messages target', async t => {
  const observed = [];
  const gateway = await fixture(t, (policy, bytes) => { observed.push({policy, body: JSON.parse(bytes)}); return response(); }, {...POLICY, provider: 'claude'});
  assert.equal((await request(gateway, {model: POLICY.model, messages: []}, {path: '/v1/messages?beta=true'})).status, 200);
  for (const path of ['/v1/messages?beta=false', '/v1/messages?beta=true&url=evil', '/v1/messages?beta=true&beta=true'])
    assert.equal((await request(gateway, BODY, {path})).status, 404);
  assert.equal(observed.length, 1);
  assert.equal(observed[0].policy.provider, 'claude');
});

async function fixture(t, transport, policy = POLICY) {
  const gateway = createGateway(policy, SECRET, CAP, transport);
  await new Promise(resolve => gateway.server.listen(0, '127.0.0.1', resolve));
  t.after(() => gateway.stop());
  return {...gateway, port: gateway.server.address().port};
}

function request(gateway, body = BODY, options = {}) {
  return new Promise((resolve, reject) => {
    const bytes = Buffer.isBuffer(body) ? body : Buffer.from(JSON.stringify(body));
    const req = http.request({hostname: '127.0.0.1', port: gateway.port, method: options.method || 'POST',
      path: options.path || '/v1/responses', headers: {authorization: 'Bearer ' + CAP,
        'content-type': 'application/json', ...options.headers}}, res => {
      const chunks = [];
      res.on('data', chunk => chunks.push(chunk));
      res.on('end', () => resolve({status: res.statusCode, text: Buffer.concat(chunks).toString(), headers: res.headers}));
    });
    req.on('error', reject);
    req.end(options.method === 'GET' ? undefined : bytes);
  });
}

test('policy and bootstrap reject unknown keys, bad limits, equal credentials', () => {
  assert.equal(validatePolicy(POLICY).provider, 'codex');
  for (const value of [{...POLICY, upstream: 'http://evil'}, {...POLICY, max_requests: true},
      {...POLICY, provider: '__proto__'}, {...POLICY, model: '../bad'}, {...POLICY, timeout_seconds: 11}])
    assert.throws(() => validatePolicy(value));
  assert.throws(() => createGateway(POLICY, CAP, CAP));
  assert.throws(() => createGateway(POLICY, 'bad\ncredential', CAP));
});

test('authentication, foreign routes, alternate hosts and method are refused', async t => {
  let calls = 0;
  const gateway = await fixture(t, () => { ++calls; return response(); });
  for (const auth of ['', 'Bearer wrong', 'Bearer ' + SECRET]) {
    assert.equal((await request(gateway, BODY, {headers: {authorization: auth}})).status, 401);
  }
  for (const path of ['/v1/responses?redirect=evil', '/v1/files', 'https://evil.invalid/v1/responses'])
    assert.equal((await request(gateway, BODY, {path})).status, 404);
  assert.equal((await request(gateway, BODY, {method: 'PUT'})).status, 404);
  assert.equal(calls, 0);
});

test('only fixed provider/model and bounded output reach transport', async t => {
  const observed = [];
  const gateway = await fixture(t, (policy, bytes, credential) => {
    observed.push({provider: policy.provider, body: JSON.parse(bytes), credential});
    return response();
  });
  assert.equal((await request(gateway, {...BODY, max_output_tokens: 99999, client_metadata: {fixture: 'synthetic'}})).status, 200);
  assert.equal(observed[0].body.max_output_tokens, 128);
  assert.equal(observed[0].body.store, false);
  assert.equal(observed[0].credential, SECRET);
  assert.equal(observed[0].provider, 'codex');
  assert.deepEqual(observed[0].body.client_metadata, {fixture: 'synthetic'});
  assert.ok(!JSON.stringify(observed[0].body).includes(SECRET));
  assert.equal((await request(gateway, {...BODY, model: 'unapproved-model'})).status, 422);
  assert.equal(observed.length, 1);
});

test('hosted tools, remote inputs, detached and stored context fail before upstream', async t => {
  let calls = 0;
  const gateway = await fixture(t, () => { ++calls; return response(); });
  for (const extra of [{tools: [{type: 'web_search'}]}, {input: [{type: 'input_image', image_url: 'https://evil'}]},
      {input: [{type: 'document'}]}, {previous_response_id: 'other'}, {background: true},
      {conversation: 'other'}, {prompt: {id: 'server-prompt'}}, {max_output_tokens: -1}, {stream: 'true'},
      {service_tier: 'priority'}, {speed: 'fast'}, {fast_mode: true}])
    assert.equal((await request(gateway, {...BODY, ...extra})).status, 422);
  assert.equal(calls, 0);
});

test('input bytes and invalid UTF-8 are rejected without attempted API usage', async t => {
  const gateway = await fixture(t, () => response());
  assert.equal((await request(gateway, {...BODY, input: 'x'.repeat(4000)})).status, 413);
  assert.equal((await request(gateway, Buffer.from([123,34,120,34,58,34,255,34,125]))).status, 422);
  assert.equal(gateway.metrics.attempted_requests, 0);
  assert.equal(gateway.metrics.upstream_failures, 0);
});

test('remote servers, stored containers and unknown request fields never reach transport', async t => {
  for (const provider of ['codex', 'claude']) {
    let calls = 0;
    const gateway = await fixture(t, () => { ++calls; return response(); }, {...POLICY, provider});
    const body = provider === 'codex' ? BODY : {model: POLICY.model, messages: []};
    const path = provider === 'codex' ? '/v1/responses' : '/v1/messages';
    for (const extra of [
      {mcp_servers: [{type: 'url', name: 'external', url: 'https://example.invalid/mcp'}]},
      {container: 'server-side-context'}, {container: {id: 'stored'}},
      {context_management: {edits: []}}, {unreviewed_future_feature: true},
      {mcp_servers: null}, {container: false},
    ]) assert.equal((await request(gateway, {...body, ...extra}, {path})).status, 422);
    assert.equal(calls, 0);
    assert.equal(gateway.metrics.attempted_requests, 0);
    assert.equal(gateway.metrics.rejected_requests, 7);
  }
});

test('local tool definitions reject remote configuration including namespace members', async t => {
  for (const provider of ['codex', 'claude']) {
    let calls = 0;
    const gateway = await fixture(t, () => { ++calls; return response(); }, {...POLICY, provider});
    const body = provider === 'codex' ? BODY : {model: POLICY.model, messages: []};
    const path = provider === 'codex' ? '/v1/responses' : '/v1/messages';
    const local = provider === 'codex' ? {type: 'function', name: 'fixture', parameters: {type: 'object'}} :
      {name: 'fixture', input_schema: {type: 'object'}};
    for (const extra of [{mcp_server_name: 'external'}, {server_url: 'https://example.invalid'},
        {allowed_callers: ['code_execution']}, {unreviewed_future_feature: true}]) {
      const remote = {...local, ...extra};
      assert.equal((await request(gateway, {...body, tools: [remote]}, {path})).status, 422);
      if (provider === 'codex')
        assert.equal((await request(gateway, {...body, tools: [{type: 'namespace', name: 'functions', tools: [remote]}]}, {path})).status, 422);
    }
    assert.equal(calls, 0);
    assert.equal(gateway.metrics.attempted_requests, 0);
    assert.equal((await request(gateway, {...body, tools: [local]}, {path})).status, 200);
    assert.equal(calls, 1);
  }
});

test('stored item references and server-tool history are refused before upstream', async t => {
  let calls = 0;
  const gateway = await fixture(t, () => { ++calls; return response(); });
  for (const type of ['item_reference', 'mcp_call', 'mcp_approval_response', 'server_tool_use'])
    assert.equal((await request(gateway, {...BODY, input: [{type, id: 'stored-item'}]})).status, 422);
  assert.equal(calls, 0);
  assert.equal(gateway.metrics.attempted_requests, 0);
});

test('redirect/error/oversize responses do not relay raw provider data', async t => {
  const replies = [{status: 302, type: 'application/json', body: Buffer.from(SECRET)},
    {status: 401, type: 'application/json', body: Buffer.from(SECRET)},
    {status: 200, type: 'application/json', body: Buffer.alloc(3000)}];
  const gateway = await fixture(t, () => replies.shift());
  for (let i = 0; i < 3; ++i) {
    const result = await request(gateway);
    assert.equal(result.status, 502);
    assert.ok(!result.text.includes(SECRET));
    assert.equal(result.headers.location, undefined);
  }
  assert.equal(gateway.metrics.attempted_requests, 3);
  assert.equal(gateway.metrics.upstream_failures, 3);
});

test('successful JSON and buffered SSE redact literal provider credentials', async t => {
  let calls = 0;
  const gateway = await fixture(t, () => ++calls === 1 ? response(SECRET) :
    {status: 200, type: 'text/event-stream; charset=utf-8', body: Buffer.from('data: ' + SECRET + '\n\n')});
  for (let i = 0; i < 2; ++i) {
    const result = await request(gateway);
    assert.equal(result.status, 200);
    assert.ok(!result.text.includes(SECRET));
    assert.ok(result.text.includes('[redacted]'));
  }
  const metrics = await request(gateway, {}, {method: 'GET', path: '/metrics'});
  assert.equal(JSON.parse(metrics.text).successful_requests, 2);
  assert.ok(!metrics.text.includes(SECRET));
  assert.ok(!metrics.text.includes('Synthetic test input'));
});

test('request quota counts failed attempts, never grants automatic retry budget', async t => {
  const gateway = await fixture(t, () => { throw new Error(SECRET); }, {...POLICY, max_requests: 1});
  const failed = await request(gateway);
  assert.equal(failed.status, 502);
  assert.ok(!failed.text.includes(SECRET));
  assert.equal((await request(gateway)).status, 429);
  assert.equal(gateway.metrics.attempted_requests, 1);
});

test('concurrency one is enforced while another request is running', async t => {
  let release, started;
  const entered = new Promise(resolve => { started = resolve; });
  const gateway = await fixture(t, () => new Promise(resolve => { release = resolve; started(); }));
  const first = request(gateway);
  await entered;
  assert.equal((await request(gateway)).status, 429);
  release(response());
  assert.equal((await first).status, 200);
  assert.equal(gateway.metrics.attempted_requests, 1);
});

test('deadline aborts transport and returns a bounded error without content', async t => {
  let aborted = false;
  const gateway = await fixture(t, (_, __, ___, signal) => new Promise((resolve, reject) => {
    signal.addEventListener('abort', () => { aborted = true; reject(new Error(SECRET)); }, {once: true});
  }));
  const result = await request(gateway);
  assert.equal(result.status, 504);
  assert.ok(aborted);
  assert.ok(!result.text.includes(SECRET));
});

test('Claude request uses its own path/output field, not Codex fields', async t => {
  let forwarded;
  const gateway = await fixture(t, (_, bytes) => { forwarded = JSON.parse(bytes); return response(); }, {...POLICY, provider: 'claude'});
  assert.equal((await request(gateway, {model: POLICY.model, messages: [], max_tokens: 9000}, {path: '/v1/messages'})).status, 200);
  assert.equal(forwarded.max_tokens, 128);
  assert.equal(forwarded.max_output_tokens, undefined);
  assert.equal((await request(gateway)).status, 404);
});

test('CONNECT and protocol upgrades cannot turn the gateway into a general proxy', async t => {
  let calls = 0;
  const gateway = await fixture(t, () => { ++calls; return response(); });
  for (const raw of ['CONNECT example.invalid:443 HTTP/1.1\r\nHost: example.invalid\r\n\r\n',
      'GET / HTTP/1.1\r\nHost: local\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n\r\n']) {
    await new Promise((resolve, reject) => {
      const socket = net.connect(gateway.port, '127.0.0.1', () => socket.write(raw));
      socket.on('data', () => {});
      socket.on('close', resolve);
      socket.on('error', reject);
      socket.setTimeout(1000, () => { socket.destroy(); reject(new Error('proxy connection did not close')); });
    });
  }
  assert.equal(calls, 0);
});

test('output-token policies do not claim an invoice or subscription cap', () => {
  const bytes = sanitizeRequest({...BODY, max_output_tokens: 42}, POLICY);
  assert.equal(JSON.parse(bytes).max_output_tokens, 42);
  assert.equal(Object.hasOwn(validatePolicy(POLICY), 'billed_usd'), false);
});

test('gateway lifetime closes its listener even without a caller stop', async t => {
  const gateway = await fixture(t, () => response(), {...POLICY, lifetime_seconds: 1});
  assert.equal((await request(gateway, {}, {method: 'GET', path: '/health'})).status, 200);
  await new Promise(resolve => gateway.server.once('close', resolve));
  await assert.rejects(request(gateway), /ECONNREFUSED|ECONNRESET|socket/i);
});

test('production transport uses fixed HTTPS/auth headers and never worker headers', async t => {
  const original = https.request;
  const observed = [];
  https.request = (options, callback) => {
    observed.push(options);
    const upstream = new EventEmitter();
    upstream.destroy = error => upstream.emit('error', error);
    upstream.end = () => {
      const stream = Readable.from([Buffer.from('{"ok":true}')]);
      stream.statusCode = 200;
      stream.headers = {'content-type': 'application/json', 'authorization': SECRET, 'location': 'https://evil.invalid'};
      callback(stream);
    };
    return upstream;
  };
  t.after(() => { https.request = original; });
  for (const provider of ['codex', 'claude']) {
    const gateway = await fixture(t, undefined, {...POLICY, provider});
    const body = provider === 'codex' ? BODY : {model: POLICY.model, messages: []};
    const result = await request(gateway, body, {path: provider === 'codex' ? '/responses' : '/v1/messages',
      headers: {'x-forwarded-host': 'evil.invalid', 'anthropic-beta': 'unapproved', 'openai-organization': 'other'}});
    assert.equal(result.status, 200);
    assert.equal(result.headers.authorization, undefined);
    assert.equal(result.headers.location, undefined);
  }
  assert.equal(observed[0].hostname, 'api.openai.com');
  assert.equal(observed[0].port, 443);
  assert.equal(observed[0].path, '/v1/responses');
  assert.equal(observed[0].headers.authorization, 'Bearer ' + SECRET);
  assert.equal(observed[1].hostname, 'api.anthropic.com');
  assert.equal(observed[1].path, '/v1/messages');
  assert.equal(observed[1].headers['x-api-key'], SECRET);
  for (const value of observed) {
    assert.equal(value.headers['x-forwarded-host'], undefined);
    assert.equal(value.headers['anthropic-beta'], undefined);
    assert.ok(!JSON.stringify(value.headers).includes(CAP));
  }
});
