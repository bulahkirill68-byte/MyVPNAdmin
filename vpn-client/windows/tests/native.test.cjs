const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs/promises')
const path = require('node:path')
const os = require('node:os')
const net = require('node:net')
const { execFile } = require('node:child_process')
const { promisify } = require('node:util')
const exec = promisify(execFile)
const assets = path.resolve(__dirname, '../assets')
test('native proxy query is read-only and returns the expected snapshot schema', async () => {
  const start = performance.now()
  const { stdout } = await exec(path.join(assets, 'native/RuntimeControl.exe'), ['proxy-read'])
  const state = JSON.parse(stdout)
  assert.deepEqual(Object.keys(state).sort(), ['AutoConfigURL', 'ProxyEnable', 'ProxyOverride', 'ProxyServer'])
  console.log('Native read-only proxy query:', Math.round(performance.now() - start), 'ms')
})
test('native core launcher creates a hidden console that supports graceful CTRL+C', async () => {
  const folder = await fs.mkdtemp(path.join(os.tmpdir(), 'reality-native-'))
  let pid
  try {
    const server = net.createServer(); await new Promise(resolve => server.listen(0, '127.0.0.1', resolve)); const port = server.address().port; await new Promise(resolve => server.close(resolve))
    const file = path.join(folder, 'config.json')
    await fs.writeFile(file, JSON.stringify({ inbounds: [{ listen: '127.0.0.1', port, protocol: 'http' }], outbounds: [{ protocol: 'blackhole' }] }))
    const result = await exec(path.join(assets, 'native/RuntimeControl.exe'), ['start-core', path.join(assets, 'engine/xray.exe'), file, path.join(folder, 'core.log'), path.join(assets, 'engine')], { timeout: 4000 }).catch(e => { pid = Number(e.stdout) || null; throw e })
    pid = Number(result.stdout); assert.ok(pid > 4)
    const alive = () => { try { process.kill(pid, 0); return true } catch { return false } }
    assert.ok(alive())
    await new Promise(resolve => setTimeout(resolve, 500))
    await exec(path.join(assets, 'native/StopConsole.exe'), [String(pid)])
    const end = Date.now() + 5000; while (alive() && Date.now() < end) await new Promise(resolve => setTimeout(resolve, 100))
    assert.equal(alive(), false, 'Core should exit on CTRL+C without forced termination')
    pid = null
  } finally {
    if (pid) await exec('taskkill.exe', ['/PID', String(pid), '/T', '/F']).catch(() => {})
    await fs.rm(folder, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 })
  }
})
