const { test } = require('node:test')
const assert = require('node:assert/strict')
const Module = require('node:module')
const fs = require('node:fs/promises')
const os = require('node:os')
const path = require('node:path')

test('stats outage preserves traffic and online health; polling recovers without restarting the VPN', async () => {
  // Exercise the real monitor, replacing only OS integration and external probes.
  const originalLoad = Module._load
  let Engine
  try {
    Module._load = function (id, parent, main) { if (id === 'electron') return { app: { isPackaged: false } }; return originalLoad.call(this, id, parent, main) }
    Engine = require('../electron/engine.cjs').Engine
  } finally { Module._load = originalLoad }
  const statsModule = require('../electron/stats.cjs'), healthModule = require('../electron/health.cjs')
  const OriginalReader = statsModule.StatsReader, originalCheck = healthModule.checkHealth
  let reads = 0, closed = false
  statsModule.StatsReader = class {
    async read() {
      ++reads
      if (reads === 2) throw Error('Temporary local gRPC failure')
      return [{ name: 'outbound>>>proxy>>>traffic>>>downlink', value: reads === 1 ? 200 : 400 }]
    }
    close() { closed = true }
  }
  healthModule.checkHealth = async () => ({ health: 'online', latency: 25, checkedAt: Date.now() })
  const folder = await fs.mkdtemp(path.join(os.tmpdir(), 'reality-monitor-'))
  const states = [], waiters = []
  const engine = new Engine(folder, () => { states.push({ ...engine.state }); for (const done of waiters) done() })
  const until = predicate => new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(Error('Monitor deadline exceeded')), 6000)
    const check = () => { if (predicate()) { clearTimeout(timer); resolve() } }
    waiters.push(check); check()
  })
  try {
    engine.prefs = { apiPort: 21915, httpPort: 21809 }; engine.state.phase = 'connected'
    engine.monitor()
    await until(() => engine.state.statsStatus === 'stale')
    assert.equal(engine.state.down, 200); assert.equal(engine.state.health, 'online'); assert.equal(engine.state.phase, 'connected')
    await until(() => reads >= 3 && engine.state.statsStatus === 'ready')
    assert.equal(engine.state.down, 400); assert.equal(engine.state.phase, 'connected')
    assert.equal(states.some(s => s.phase === 'disconnected'), false)
    await engine.stop(); assert.ok(closed)
  } finally {
    await engine.stop(); statsModule.StatsReader = OriginalReader; healthModule.checkHealth = originalCheck
    await fs.rm(folder, { recursive: true, force: true })
  }
})
