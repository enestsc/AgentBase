'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const https = require('node:https');
const {responseFixture, command, resultMarker, evalEvidence, MARKER} = require('../src/agentbase/assets/native-mock.cjs');

test('synthetic Responses and Messages frames are deterministic without upstream transport', t => {
  const original = https.request;
  https.request = () => { throw new Error('must never call a provider'); };
  t.after(() => { https.request = original; });
  for (const provider of ['codex', 'claude']) {
    const json = responseFixture(provider, {model: 'synthetic-model', stream: false});
    assert.equal(json.type, 'application/json');
    assert.ok(JSON.stringify(JSON.parse(json.body)).includes(MARKER));
    const stream = responseFixture(provider, {model: 'synthetic-model', stream: true});
    assert.equal(stream.type, 'text/event-stream');
    const frames = stream.body.toString().trim().split('\n\n').map(frame => JSON.parse(frame.split('\ndata: ')[1]));
    assert.ok(frames.length >= 6);
    assert.equal(frames.at(-1).type, provider === 'codex' ? 'response.completed' : 'message_stop');
  }
});

test('fixed commands isolate environment, disable tools/web and refuse unknown modes', () => {
  for (const provider of ['codex', 'claude']) {
    const value = command(provider, 'http://127.0.0.1:1234', 'synthetic-capability');
    assert.equal(value.environment.HOME, '/tmp/home');
    assert.equal(value.environment.DISABLE_TELEMETRY, '1');
    assert.equal(value.environment.AWS_SECRET_ACCESS_KEY, undefined);
    assert.equal(value.environment.OPENAI_API_KEY, undefined);
    assert.ok(!value.arguments.some(arg => arg.includes('dangerously')));
    assert.ok(!value.arguments.includes('synthetic-capability'));
  }
  const codex = command('codex', 'http://127.0.0.1:1234', 'synthetic-capability');
  assert.ok(codex.arguments.includes('web_search="disabled"'));
  assert.ok(codex.arguments.includes('--ignore-user-config'));
  const evaluation = command('claude', 'http://127.0.0.1:1234', 'synthetic-capability', 'eval');
  for (const flag of ['--no-publish', '--no-scaffold', '--trust-plugin', '--mocks', '--max-cost-usd'])
    assert.ok(evaluation.arguments.includes(flag));
  assert.ok(!evaluation.arguments.includes('--allow-real-servers'));
  assert.throws(() => command('codex', 'unused', 'unused', 'eval'));
  assert.throws(() => command('unknown', 'unused', 'unused'));
});

test('native marker evidence rejects incomplete, error and tool-using traces', () => {
  const codex = [{type: 'item.completed', item: {type: 'agent_message', text: MARKER}}, {type: 'turn.completed'}];
  const claude = [{type: 'system', subtype: 'init'}, {type: 'result', subtype: 'success', is_error: false, num_turns: 1, result: MARKER}];
  const lines = value => value.map(event => JSON.stringify(event)).join('\n');
  assert.ok(resultMarker('codex', lines(codex)));
  assert.ok(resultMarker('claude', lines(claude)));
  assert.equal(resultMarker('codex', lines(codex.slice(0, 1))), false);
  assert.equal(resultMarker('codex', lines([...codex, {type: 'turn.failed'}])), false);
  assert.equal(resultMarker('codex', lines([{type: 'item.completed', item: {type: 'command_execution'}}, ...codex])), false);
  assert.equal(resultMarker('claude', lines([...claude, claude.at(-1)])), false);
  assert.equal(resultMarker('claude', lines([{type: 'assistant', message: {content: [{type: 'tool_use'}]}}, ...claude])), false);
  assert.throws(() => resultMarker('claude', lines(claude) + '\nnot-json'));
});

test('eval evidence needs a complete versioned single-case single-arm result', () => {
  const value = {schemaVersion: 1, partial: false, aggregates: {casesTotal: 1, casesPassed: 1, overallScore: 1},
    cases: [{arms: {with: [{error: null}], without: []}}]};
  assert.deepEqual(evalEvidence(JSON.stringify(value)), {cases_total: 1, cases_passed: 1, score_is_one: true, run_error: false});
  assert.throws(() => evalEvidence(JSON.stringify({...value, partial: true})));
  assert.throws(() => evalEvidence(JSON.stringify({...value, schemaVersion: 2})));
  assert.throws(() => evalEvidence(JSON.stringify({...value, cases: [{arms: {with: [{error: null}], without: [{error: null}]}}]})));
  value.cases[0].arms.with[0].error = 'synthetic failure';
  assert.equal(evalEvidence(JSON.stringify(value)).run_error, true);
});
