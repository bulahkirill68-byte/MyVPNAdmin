// Cold and warm launches of the actual self-contained EXE, with isolated user data.
const { chromium } = require('playwright')
const { spawn } = require('node:child_process')
const fs = require('node:fs/promises')
const path = require('node:path')
const os = require('node:os')
const net = require('node:net')
const assert = require('node:assert/strict')
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
;(async () => {
  const root = path.resolve(__dirname, '../../releases/windows')
  const pkg = require('../package.json')
  const executable = process.argv[2] ? path.resolve(process.argv[2]) : path.join(root, `RealityVPN-${pkg.version}-portable.exe`)
  const data = await fs.mkdtemp(path.join(os.tmpdir(), 'reality-portable-'))
  const measurements = []
  let browser, page
  try {
    const metadata = !process.argv[2] ? JSON.parse(await fs.readFile(path.join(root, 'portable-build.json'), 'utf8')) : null
    const cache = metadata ? path.join(process.env.LOCALAPPDATA, 'RealityVPNClient/portable', metadata.buildKey, 'resources/app.asar') : null
    let unpackedAt
    for (const run of ['first', 'repeat']) {
      const listener = net.createServer(); await new Promise(resolve => listener.listen(0, '127.0.0.1', resolve)); const port = listener.address().port; await new Promise(resolve => listener.close(resolve))
      const started = performance.now()
      const launcher = spawn(executable, ['--user-data-dir=' + data, '--remote-debugging-port=' + port, '--remote-debugging-address=127.0.0.1'], { stdio: 'ignore' })
      launcher.on('error', e => console.error(e))
      const deadline = Date.now() + 120000
      while (Date.now() < deadline) {
        try { browser = await chromium.connectOverCDP(`http://127.0.0.1:${port}`, { timeout: 700 }); break } catch { await delay(100) }
      }
      assert.ok(browser, 'Portable should start within deadline')
      const context = browser.contexts()[0]; page = context.pages()[0] || await context.waitForEvent('page')
      await page.getByRole('heading', { name: 'Свобода подключения.' }).waitFor()
      const launchMs = Math.round(performance.now() - started)
      const version = await page.evaluate(async () => (await window.reality.initial()).version)
      measurements.push({ run, launchMs, version })
      if (cache) { const time = (await fs.stat(cache)).mtimeMs; if (unpackedAt) assert.equal(time, unpackedAt, 'Warm launch must reuse extracted files'); unpackedAt = time }
      await page.evaluate(() => { void window.reality.close() })
      await browser.close().catch(() => {}); browser = null; page = null
      await delay(1000)
    }
    const report = { executable: path.basename(executable), measurements }
    console.log(JSON.stringify(report, null, 2))
    await fs.writeFile(path.join(root, `startup-benchmark-${measurements[0].version}.json`), JSON.stringify(report, null, 2))
  } finally {
    if (page) await page.evaluate(() => { void window.reality.close() }).catch(() => {})
    if (browser) await browser.close().catch(() => {})
    await delay(500); await fs.rm(data, { recursive: true, force: true, maxRetries: 5, retryDelay: 500 })
  }
})().catch(e => { console.error(e); process.exitCode = 1 })
