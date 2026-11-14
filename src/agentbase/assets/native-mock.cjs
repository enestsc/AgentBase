'use strict';

// First-party synthetic protocol probe. Run ONLY in the verified network=none
// container boundary. There is no real key, provider transport or user prompt.
const fs = require('node:fs');
const crypto = require('node:crypto');
const {spawn} = require('node:child_process');
const {createGateway} = require('./gateway.cjs');

const MARKER = 'AGENTBASE_FIXTURE_OK';
const SECRET = 'agentbase-synthetic-not-a-provider-key';

function responseFixture(provider, body) {
  const usage = {input_tokens: 8, output_tokens: 4};
  if (provider === 'claude') {
    const message = {id: 'msg_fixture', type: 'message', role: 'assistant', model: body.model,
      content: [{type: 'text', text: MARKER}], stop_reason: 'end_turn', stop_sequence: null,
      usage: {...usage, cache_creation_input_tokens: 0, cache_read_input_tokens: 0}};
    if (!body.stream) return {type: 'application/json', body: Buffer.from(JSON.stringify(message))};
    const events = [
      ['message_start', {type: 'message_start', message: {...message, content: [], stop_reason: null}}],
      ['content_block_start', {type: 'content_block_start', index: 0, content_block: {type: 'text', text: ''}}],
      ['content_block_delta', {type: 'content_block_delta', index: 0, delta: {type: 'text_delta', text: MARKER}}],
      ['content_block_stop', {type: 'content_block_stop', index: 0}],
      ['message_delta', {type: 'message_delta', delta: {stop_reason: 'end_turn', stop_sequence: null}, usage: {output_tokens: 4}}],
      ['message_stop', {type: 'message_stop'}]
    ];
    return {type: 'text/event-stream', body: Buffer.from(events.map(([event, value]) => `event: ${event}\ndata: ${JSON.stringify(value)}\n\n`).join(''))};
  }
  const item = {id: 'msg_fixture', type: 'message', role: 'assistant', status: 'completed',
    content: [{type: 'output_text', text: MARKER, annotations: []}]};
  const response = {id: 'resp_fixture', object: 'response', created_at: 1, model: body.model,
    status: 'completed', output: [item], usage: {...usage, total_tokens: 12,
      input_tokens_details: {cached_tokens: 0}, output_tokens_details: {reasoning_tokens: 0}}};
  if (!body.stream) return {type: 'application/json', body: Buffer.from(JSON.stringify(response))};
  const events = [
    {type: 'response.created', response: {...response, output: [], status: 'in_progress'}},
    {type: 'response.output_item.added', output_index: 0, item: {...item, content: [], status: 'in_progress'}},
    {type: 'response.content_part.added', item_id: item.id, output_index: 0, content_index: 0,
      part: {type: 'output_text', text: '', annotations: []}},
    {type: 'response.output_text.delta', item_id: item.id, output_index: 0, content_index: 0, delta: MARKER},
    {type: 'response.output_text.done', item_id: item.id, output_index: 0, content_index: 0, text: MARKER},
    {type: 'response.content_part.done', item_id: item.id, output_index: 0, content_index: 0, part: item.content[0]},
    {type: 'response.output_item.done', output_index: 0, item},
    {type: 'response.completed', response}
  ];
  return {type: 'text/event-stream', body: Buffer.from(events.map((value, sequence_number) =>
    `event: ${value.type}\ndata: ${JSON.stringify({...value, sequence_number})}\n\n`).join(''))};
}

function command(provider, base, capability, mode = 'print') {
  if (!['codex', 'claude'].includes(provider) || !['print', 'eval'].includes(mode) || (mode === 'eval' && provider !== 'claude'))
    throw new Error('synthetic command refused');
  const environment = {PATH: '/usr/local/bin:/usr/bin:/bin', HOME: '/tmp/home', TMPDIR: '/tmp',
    CODEX_HOME: '/tmp/home/codex', CLAUDE_CONFIG_DIR: '/tmp/home/claude',
    DISABLE_AUTOUPDATER: '1', DISABLE_TELEMETRY: '1', OTEL_SDK_DISABLED: 'true',
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: '1', CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS: '1'};
  const prompt = `Reply with exactly ${MARKER}. Do not call any tools.`;
  if (provider === 'codex') {
    environment.AGENTBASE_FIXTURE_CAPABILITY = capability;
    const settings = {model_provider: 'fixture', model: 'agentbase-fixture', web_search: 'disabled', 'features.multi_agent': false,
      'model_providers.fixture.name': 'AgentBase synthetic fixture',
      'model_providers.fixture.base_url': base + '/v1', 'model_providers.fixture.env_key': 'AGENTBASE_FIXTURE_CAPABILITY',
      'model_providers.fixture.wire_api': 'responses', 'model_providers.fixture.request_max_retries': 0,
      'model_providers.fixture.stream_max_retries': 0, 'model_providers.fixture.supports_websockets': false};
    return {environment, arguments: ['exec', '--json', '--ephemeral', '--ignore-rules', '--ignore-user-config',
      '--skip-git-repo-check', '--sandbox', 'read-only', ...Object.entries(settings).flatMap(([key, value]) => ['-c', key + '=' + JSON.stringify(value)]), prompt]};
  }
  environment.ANTHROPIC_BASE_URL = base;
  environment.ANTHROPIC_API_KEY = capability;
  environment.API_TIMEOUT_MS = '15000';
  if (mode === 'eval') return {environment, arguments: ['plugin', 'eval', '/tmp/plugin', '--json', '--model', 'claude-fixture',
    '--runs', '1', '--concurrency', '1', '--ablation', 'none', '--max-cost-usd', '0.01',
    '--no-publish', '--no-scaffold', '--trust-plugin', '--mocks', 'record']};
  return {environment, arguments: ['--print', '--output-format', 'stream-json', '--verbose', '--model', 'claude-fixture', '--tools', '',
    '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}', '--setting-sources', '',
    '--settings', '{"disableAllHooks":true}', '--plugin-dir', '/tmp/plugin', '--no-session-persistence', '--max-turns', '1', '--max-budget-usd', '0.01', prompt]};
}

function resultMarker(provider, text) {
  const events = text.trim().split('\n').map(line => JSON.parse(line));
  if (provider === 'claude') {
    const results = events.filter(value => value.type === 'result');
    return results.length === 1 && results[0] === events.at(-1) && results[0].is_error === false &&
      results[0].subtype === 'success' && results[0].num_turns === 1 && results[0].result === MARKER &&
      !events.some(value => value.type === 'assistant' && value.message?.content?.some(block => block.type === 'tool_use'));
  }
  const messages = events.filter(value => value.type === 'item.completed' && value.item?.type === 'agent_message');
  return messages.length === 1 && messages[0].item.text === MARKER && events.at(-1)?.type === 'turn.completed' &&
    !events.some(value => value.type === 'turn.failed' || ['command_execution', 'mcp_tool_call', 'web_search', 'file_change'].includes(value.item?.type));
}

function evalEvidence(text) {
  const value = JSON.parse(text);
  if (value.schemaVersion !== 1 || !Array.isArray(value.cases) || value.cases.length !== 1 || value.partial !== false)
    throw new Error('eval result schema refused');
  const runs = value.cases[0].arms?.with;
  const without = value.cases[0].arms?.without || [];
  if (!Array.isArray(runs) || runs.length !== 1 || !Array.isArray(without) || without.length !== 0)
    throw new Error('eval arms refused');
  return {cases_total: value.aggregates?.casesTotal === 1 ? 1 : 0,
    cases_passed: value.aggregates?.casesPassed === 1 ? 1 : 0,
    score_is_one: value.aggregates?.overallScore === 1, run_error: runs[0].error !== null};
}

function preparePlugin(mode) {
  const files = JSON.parse(fs.readFileSync('/program/native-plugin.json', 'utf8'));
  for (const [name, content] of Object.entries(files)) {
    if (!/^[A-Za-z0-9_.\/-]+$/.test(name) || name.startsWith('/') || name.split('/').some(p => !p || p === '.' || p === '..') || typeof content !== 'string')
      throw new Error('canonical plugin path refused');
    const target = '/tmp/plugin/' + name;
    fs.mkdirSync(require('node:path').dirname(target), {recursive: true, mode: 0o700});
    fs.writeFileSync(target, content, {flag: 'wx', mode: 0o600});
  }
  if (mode === 'eval') {
    const path = '/tmp/plugin/evals/fixture';
    fs.mkdirSync(path + '/graders', {recursive: true, mode: 0o700});
    fs.writeFileSync(path + '/prompt.md', `---\nname: fixture\nruns: 1\nmodel: claude-fixture\nmax_turns: 1\ntimeout_seconds: 20\nallowed_tools: []\n---\nReply with exactly ${MARKER}. Do not call tools.\n`);
    fs.writeFileSync(path + '/graders/marker.md', `---\ntype: regex\ntarget: last_message\npattern: '^${MARKER}$'\n---\n`);
  }
}

async function main(provider, mode = 'print') {
  if (!['codex', 'claude'].includes(provider) || !['print', 'eval'].includes(mode) || (mode === 'eval' && provider !== 'claude'))
    throw new Error('provider/mode refused');
  fs.mkdirSync('/tmp/home', {recursive: true, mode: 0o700});
  for (const name of ['codex', 'claude']) fs.mkdirSync('/tmp/home/' + name, {mode: 0o700});
  if (provider === 'claude') preparePlugin(mode);
  const capability = crypto.randomBytes(32).toString('hex');
  let fixtureRequests = 0;
  const policy = {schema_version: 1, provider, model: provider === 'codex' ? 'agentbase-fixture' : 'claude-fixture',
    max_requests: 2, max_output_tokens: 128, max_request_bytes: 500000, max_response_bytes: 65536,
    timeout_seconds: 15, lifetime_seconds: 60};
  const gateway = createGateway(policy, SECRET, capability, async (_, bytes, credential) => {
    if (credential !== SECRET) throw new Error('synthetic credential mismatch');
    ++fixtureRequests;
    return {status: 200, ...responseFixture(provider, JSON.parse(bytes))};
  });
  await new Promise((resolve, reject) => { gateway.server.once('error', reject); gateway.server.listen(0, '127.0.0.1', resolve); });
  const configured = command(provider, 'http://127.0.0.1:' + gateway.server.address().port, capability, mode);
  let raw = '', diagnostics = '', overflow = false;
  try {
    const child = spawn('/usr/local/bin/' + provider, configured.arguments,
      {env: configured.environment, cwd: '/tmp/home', stdio: ['ignore', 'pipe', 'pipe']});
    const timer = setTimeout(() => child.kill('SIGKILL'), 45000);
    const collect = (chunk, stderr) => {
      if (Buffer.byteLength(raw) + Buffer.byteLength(diagnostics) + chunk.length > 500000) {
        overflow = true; child.kill('SIGKILL');
      } else if (stderr) diagnostics += chunk.toString('utf8');
      else raw += chunk.toString('utf8');
    };
    child.stdout.on('data', chunk => collect(chunk, false));
    child.stderr.on('data', chunk => collect(chunk, true));
    const exitCode = await new Promise(resolve => {
      child.once('error', () => resolve(null)); child.once('close', resolve);
    });
    clearTimeout(timer);
    let marker = false, pluginDiscovered = false, evaluation = null;
    try {
      if (mode === 'eval') {
        evaluation = evalEvidence(raw);
        marker = !overflow && evaluation.cases_total === 1 && evaluation.cases_passed === 1 && evaluation.score_is_one && !evaluation.run_error;
      } else {
        marker = !overflow && resultMarker(provider, raw);
        if (provider === 'claude') pluginDiscovered = raw.trim().split('\n').map(line => JSON.parse(line)).some(value =>
          value.type === 'system' && value.subtype === 'init' && Array.isArray(value.plugins) && value.plugins.some(plugin => plugin.name === 'agentbase'));
      }
    } catch { /* Untrusted/changed native output fails closed. */ }
    // Never relay native messages, stderr, prompts, headers or trace contents.
    process.stdout.write(JSON.stringify({schema_version: 1, provider, mode, origin: 'mock', exit_code: exitCode,
      marker_verified: marker, fixture_requests: fixtureRequests, gateway_metrics: gateway.metrics,
      canonical_plugin_discovered: pluginDiscovered, eval_evidence: evaluation,
      output_overflow: overflow, provider_api_calls: 0, actual_model_behavior_verified: false}) + '\n');
  } finally { gateway.stop(); }
}

if (require.main === module) main(process.argv[2], process.argv[3]).catch(() => { process.stderr.write('Synthetic native probe failed\n'); process.exitCode = 2; });
module.exports = {responseFixture, command, resultMarker, evalEvidence, MARKER};
