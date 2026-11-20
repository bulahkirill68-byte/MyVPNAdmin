// Real packaged application and core smoke check. Does not change system proxy or routes.
const { _electron: electron } = require('playwright')
const assert = require('node:assert/strict')
const fs = require('node:fs/promises')
const os = require('node:os')
const path = require('node:path')
const { execFileSync } = require('node:child_process')
const { parseVless } = require('../shared/profile.cjs')
const { buildConfig } = require('../shared/config.cjs')
const uri = 'vless://12345678-1234-1234-1234-123456789abc@203.0.113.1:443?security=reality&type=tcp&pbk=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA&sid=aabb&sni=example.com#Smoke%20test'
;(async () => {
  const folder = await fs.mkdtemp(path.join(os.tmpdir(), 'reality-smoke-'))
  const executablePath = path.resolve(__dirname, '../../releases/windows/win-unpacked/Reality VPN.exe')
  let app
  let previousClipboard
  try {
    // Config validation reads the actual bundled geodata, but creates no TUN adapter.
    for (const mode of ['proxy', 'vpn']) {
      const config = path.join(folder, mode + '.json')
      await fs.writeFile(config, JSON.stringify(buildConfig(parseVless(uri), {}, mode)))
      const output = execFileSync(path.join(path.dirname(executablePath), 'resources/engine/xray.exe'), ['run', '-test', '-config', config], { env: { ...process.env, XRAY_LOCATION_ASSET: path.join(path.dirname(executablePath), 'resources/engine') } }).toString()
      assert.match(output, /Configuration OK/)
    }
    const launchStarted = performance.now()
    app = await electron.launch({ executablePath, args: ['--user-data-dir=' + folder], timeout: 30000 })
    previousClipboard = await app.evaluate(async ({ clipboard }) => await clipboard.readText())
    await app.evaluate(async ({ clipboard }, value) => await clipboard.writeText(value), uri)
    const window = await app.firstWindow()
    const failures = []
    window.on('pageerror', e => failures.push(e.message))
    await window.getByRole('heading', { name: 'Свобода подключения.' }).waitFor()
    const launchMs = Math.round(performance.now() - launchStarted)
    const initial = await window.evaluate(() => window.reality.initial())
    assert.equal(initial.profiles.length, 0)
    // Test the settings switch through IPC without changing this PC's actual login items.
    await app.evaluate(({ app }) => {
      let enabled = false
      globalThis.smokeLoginCalls = []
      globalThis.smokeLoginOriginal = { read: app.getLoginItemSettings, write: app.setLoginItemSettings }
      app.getLoginItemSettings = () => ({ openAtLogin: enabled, executableWillLaunchAtLogin: enabled })
      app.setLoginItemSettings = options => { globalThis.smokeLoginCalls.push(options); enabled = options.openAtLogin }
    })
    await window.getByRole('button', { name: 'Настройки', exact: true }).click()
    const startupSwitch = window.getByRole('switch', { name: /Запускать при входе в Windows/ })
    await startupSwitch.check()
    await window.waitForFunction(async () => (await window.reality.initial()).startup.enabled)
    await startupSwitch.uncheck()
    await window.waitForFunction(async () => !(await window.reality.initial()).startup.enabled)
    assert.deepEqual(await app.evaluate(() => globalThis.smokeLoginCalls.map(call => call.openAtLogin)), [true, false])
    await app.evaluate(({ app }) => { app.getLoginItemSettings = globalThis.smokeLoginOriginal.read; app.setLoginItemSettings = globalThis.smokeLoginOriginal.write })
    await window.getByRole('button', { name: /Мои серверы/ }).click()
    await window.getByRole('button', { name: 'Импортировать ссылку' }).click()
    await window.getByRole('button', { name: 'Вставить', exact: true }).click()
    await window.waitForFunction(value => document.querySelector('textarea')?.value === value, uri)
    await window.getByRole('button', { name: 'Добавить сервер', exact: true }).click()
    await window.getByRole('heading', { name: 'Smoke test' }).waitFor()
    const imported = await window.evaluate(() => window.reality.initial())
    assert.equal(imported.profiles[0].fingerprint, 'firefox')
    assert.ok(!JSON.stringify(imported).includes('12345678-1234'))
    await app.evaluate(async ({ clipboard }) => await clipboard.writeText(''))
    await window.evaluate(id => window.reality.copyAccess(id), imported.selected)
    assert.equal(await app.evaluate(async ({ clipboard }) => await clipboard.readText()), uri)
    await app.evaluate(async ({ clipboard }, value) => await clipboard.writeText(value), previousClipboard)
    previousClipboard = undefined
    await window.evaluate(prefs => window.reality.savePrefs({ ...prefs, manageProxy: false, socksPort: 21808, httpPort: 21809, apiPort: 21915 }), imported.prefs)
    await window.getByRole('button', { name: 'Подключение', exact: true }).click()
    const connectStarted = performance.now()
    await window.getByRole('button', { name: 'Подключить', exact: true }).click()
    await window.waitForFunction(async () => (await window.reality.initial()).connection.phase === 'connected')
    const connectMs = Math.round(performance.now() - connectStarted)
    // The documentation-only endpoint cannot work. A running core must NOT show green/online.
    await window.getByRole('heading', { name: 'Нет подтверждения доступа' }).waitFor({ timeout: 15000 })
    await window.waitForFunction(async () => (await window.reality.initial()).connection.statsStatus === 'ready')
    const active = await window.evaluate(() => window.reality.initial())
    assert.equal(active.connection.health, 'degraded')
    assert.equal(active.connection.phase, 'connected')
    await window.screenshot({ path: path.resolve(__dirname, '../../releases/windows/screenshot-degraded.png') })
    await window.getByRole('button', { name: 'Отключить', exact: true }).click()
    await window.getByRole('heading', { name: 'Подключитесь к свободе' }).waitFor()
    await window.waitForFunction(async () => (await window.reality.initial()).connection.phase === 'disconnected')
    await window.getByText('Готов к подключению', { exact: true }).waitFor()
    await window.screenshot({ path: path.resolve(__dirname, '../../releases/windows/screenshot.png') })
    assert.deepEqual(failures, [])
    await app.close(); app = null
    const encrypted = await fs.readFile(path.join(folder, 'profiles.enc'))
    assert.ok(!encrypted.includes(Buffer.from('12345678-1234')))
    assert.equal(await fs.stat(path.join(folder, 'runtime.json')).then(() => true, () => false), false)
    console.log(JSON.stringify({ launchMs, connectMs, stages: active.connection.timings }))
    console.log('PASS: packaged UI, clipboard, DPAPI vault, actual Xray startup/stats/shutdown, unreachable server stays amber, proxy and TUN config validation. System proxy and routes untouched.')
  } finally { if (app) { if (previousClipboard !== undefined) await app.evaluate(async ({ clipboard }, value) => await clipboard.writeText(value), previousClipboard).catch(() => {}); await app.close() } await fs.rm(folder, { recursive: true, force: true, maxRetries: 5, retryDelay: 500 }) }
})().catch(e => { console.error(e); process.exitCode = 1 })
