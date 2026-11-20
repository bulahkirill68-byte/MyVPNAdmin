const { test } = require('node:test')
const assert = require('node:assert/strict')
const { TrafficTracker, decode } = require('../electron/stats.cjs')
const { checkHealth } = require('../electron/health.cjs')
const stat = (direction, value) => ({ name: `outbound>>>proxy>>>traffic>>>${direction}`, value })
test('traffic keeps totals through missing counters, resets, and recovery; speed uses elapsed sample time', () => {
  const tracker = new TrafficTracker()
  assert.deepEqual(tracker.sample([stat('uplink', 100), stat('downlink', 200)], 1000), { up: 100, down: 200, upRate: 0, downRate: 0, statsAt: 1000, statsStatus: 'ready' })
  assert.equal(tracker.sample([], 2000).down, 200)
  const updated = tracker.sample([stat('uplink', 200), stat('downlink', 400)], 4000)
  assert.equal(updated.up, 200); assert.equal(updated.downRate, 100)
  const reset = tracker.sample([stat('downlink', 50)], 5000)
  assert.equal(reset.down, 450); assert.equal(reset.up, 200)
})
test('stats decoder tolerates protocol extensions but rejects truncated messages', () => {
  // QueryStatsResponse stat { name:"x", value:150 } plus an unknown top-level field.
  assert.deepEqual(decode(Buffer.from([10, 6, 10, 1, 120, 16, 150, 1, 16, 1])), [{ name: 'x', value: 150 }])
  assert.throws(() => decode(Buffer.from([10, 99, 10])))
})
test('health checks always use the localhost proxy; one HTTPS target suffices', async () => {
  const calls = []
  const result = await checkHealth(23456, { request: async (url, agent) => {
    calls.push(url); assert.equal(agent.proxy.hostname, '127.0.0.1'); assert.equal(agent.proxy.port, '23456')
    if (url.includes('cloudflare')) throw Error('Blocked endpoint')
    return 125
  } })
  assert.equal(result.health, 'online'); assert.equal(result.latency, 125); assert.equal(calls.length, 2)
})
test('failed probes produce degraded state independently of running core/statistics', async () => {
  const result = await checkHealth(23456, { request: async () => { throw Error('unreachable') } })
  assert.equal(result.health, 'degraded'); assert.equal(result.latency, null)
})
test('health probes have a total deadline and can be cancelled on disconnect', async () => {
  const hang = (_url, _agent, signal) => new Promise((resolve, reject) => { if (signal.aborted) reject(Error('aborted')); else signal.addEventListener('abort', () => reject(Error('aborted')), { once: true }) })
  const result = await checkHealth(23456, { request: hang, timeout: 25 })
  assert.equal(result.health, 'degraded')
  const controller = new AbortController(); controller.abort()
  assert.equal(await checkHealth(23456, { request: hang, signal: controller.signal }), null)
})
