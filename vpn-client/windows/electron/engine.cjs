const { app } = require('electron')
const fs = require('node:fs/promises')
const path = require('node:path')
const crypto = require('node:crypto')
const net = require('node:net')
const { spawn, execFile } = require('node:child_process')
const { promisify } = require('node:util')
const { buildConfig } = require('../shared/config.cjs')
const { control, readProxy, setProxy, restoreProxy } = require('./proxy.cjs')
const exec = promisify(execFile)
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
async function available(port) {
  const server = net.createServer()
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(port, '127.0.0.1', resolve) })
  const result = server.address().port
  await new Promise(resolve => server.close(resolve))
  return result
}
function listening(port) {
  return new Promise(resolve => {
    const socket = net.connect({ host: '127.0.0.1', port })
    const finish = result => { socket.destroy(); resolve(result) }
    socket.setTimeout(250); socket.once('connect', () => finish(true)); socket.once('error', () => finish(false)); socket.once('timeout', () => finish(false))
  })
}
class Engine {
  constructor(directory, notify) {
    this.directory = directory; this.notify = notify; this.generation = 0
    this.state = { phase: 'disconnected', stage: '', health: 'unknown', healthMessage: '', latency: null, checkedAt: 0, lastOnline: 0, statsStatus: 'pending', statsAt: 0, error: '', up: 0, down: 0, upRate: 0, downRate: 0, since: 0, timings: {} }
    this.assets = app.isPackaged ? process.resourcesPath : path.join(__dirname, '../assets')
    this.journal = path.join(directory, 'proxy-recovery.json')
  }
  update(patch) { Object.assign(this.state, patch); this.notify() }
  async recover() {
    try { const saved = JSON.parse(await fs.readFile(this.journal, 'utf8')); await restoreProxy(saved.previous, saved.port); await fs.rm(this.journal) }
    catch (e) { if (e.code !== 'ENOENT') throw Error('Не удалось восстановить системный прокси: ' + e.message) }
  }
  prepare() {
    if (!this.preparing) this.preparing = this.recover().then(async () => {
      const manifest = JSON.parse(await fs.readFile(path.join(this.assets, 'engine/integrity.json'), 'utf8'))
      await Promise.all([['engine/xray.exe', 'xray.exe'], ['native/RuntimeControl.exe', 'RuntimeControl.exe']].map(async ([file, key]) => {
        if (crypto.createHash('sha256').update(await fs.readFile(path.join(this.assets, file))).digest('hex') !== manifest[key]) throw Error('Повреждён файл ' + key)
      }))
      // Warm JS modules after the window is visible, outside the connect critical path.
      require('@grpc/grpc-js'); require('./health.cjs')
    })
    return this.preparing
  }
  async helperRequest(route, method = 'GET') {
    const response = await fetch(`http://127.0.0.1:${this.session.port}${route}`, { method, headers: { Authorization: `Bearer ${this.session.token}` }, signal: AbortSignal.timeout(1200) })
    if (!response.ok) throw Error('VPN helper: ' + response.status)
    return response.json()
  }
  async start(profile, prefs, mode) {
    if (this.state.phase !== 'disconnected') throw Error('Сначала отключите текущее соединение')
    const started = performance.now(), timings = {}
    const mark = name => { timings[name] = Math.round(performance.now() - started) }
    this.update({ phase: 'connecting', stage: 'Подготовка ядра', mode, error: '', health: 'checking', healthMessage: '', checkedAt: 0, lastOnline: 0, statsStatus: 'pending', statsAt: 0, latency: null, up: 0, down: 0, upRate: 0, downRate: 0, timings })
    this.prefs = prefs; this.coreExited = false
    try {
      await this.prepare()
      await Promise.all([prefs.socksPort, prefs.httpPort, prefs.apiPort].map(available))
      await fs.mkdir(this.directory, { recursive: true }); mark('preparedMs')
      const engine = path.join(this.assets, 'engine/xray.exe')
      if (mode === 'vpn') {
        this.update({ stage: 'Подтвердите запрос Windows (UAC)' })
        this.session = { token: crypto.randomBytes(32).toString('hex'), port: await available(0), parentPid: process.pid, created: Date.now(), uri: profile.uri, prefs }
        this.sessionFile = path.join(this.directory, 'vpn-session.enc')
        const { safeStorage } = require('electron')
        await fs.writeFile(this.sessionFile, safeStorage.encryptString(JSON.stringify(this.session)))
        await control(['elevate', process.execPath, this.sessionFile, ...(!app.isPackaged ? [app.getAppPath()] : [])], 120000)
      } else {
        this.configFile = path.join(this.directory, 'runtime.json')
        await fs.writeFile(this.configFile, JSON.stringify(buildConfig(profile, prefs, mode)))
        const child = spawn(engine, ['run', '-config', this.configFile], { windowsHide: true, env: { ...process.env, XRAY_LOCATION_ASSET: path.join(this.assets, 'engine') }, stdio: ['ignore', 'pipe', 'pipe'] })
        this.child = child; this.coreError = ''
        const log = chunk => { this.coreError = (this.coreError + chunk.toString().replaceAll(profile.uuid, '[UUID]')).slice(-1200) }
        child.stdout.on('data', log); child.stderr.on('data', log)
        child.on('error', e => { this.coreError = e.message; this.coreExited = true })
        child.on('exit', () => { if (this.child !== child) return; this.coreExited = true; if (this.state.phase === 'connected') void this.fail('Xray остановлен: ' + this.coreError) })
      }
      mark('spawnedMs'); this.update({ stage: 'Запуск локального туннеля' })
      const end = Date.now() + 15000
      let ready = false
      while (Date.now() < end) {
        if (this.coreExited) throw Error(this.coreError || 'Xray завершился')
        if (this.session) {
          const status = await this.helperRequest('/state').catch(() => null)
          if (status?.phase === 'error') throw Error(status.error)
          if (status?.stage && status.stage !== this.state.stage) this.update({ stage: status.stage })
          if (status?.phase !== 'running') { await delay(100); continue }
        }
        if (await listening(prefs.httpPort)) { ready = true; break }
        await delay(80)
      }
      if (!ready) throw Error('Локальное ядро не запустилось за 15 секунд')
      mark('coreReadyMs')
      if (mode === 'proxy' && prefs.manageProxy) {
        this.update({ stage: 'Настройка системного прокси' })
        const previous = await readProxy()
        await fs.writeFile(this.journal, JSON.stringify({ previous, port: prefs.httpPort }))
        await setProxy(prefs.httpPort)
      }
      mark('connectedMs')
      this.update({ phase: 'connected', stage: '', since: Date.now(), health: 'checking', healthMessage: 'Проверяем доступ через сервер', timings: { ...timings } })
      this.monitor()
    } catch (error) { await this.stop(); this.update({ error: error.message }); throw error }
    finally { if (this.sessionFile) { await fs.rm(this.sessionFile, { force: true }).catch(() => {}); this.sessionFile = null } }
  }
  monitor() {
    const { StatsReader, TrafficTracker } = require('./stats.cjs')
    const generation = ++this.generation, current = () => generation === this.generation && this.state.phase === 'connected'
    this.stats = new StatsReader(this.prefs.apiPort); const tracker = new TrafficTracker()
    let polling = false, helperFailures = 0
    const sample = async () => {
      if (!current() || polling) return
      polling = true
      // A stats-channel failure must not tear down a working VPN or erase counters.
      try { const stats = await this.stats.read(); if (current()) this.update(tracker.sample(stats)) }
      catch { if (current()) this.update({ statsStatus: 'stale', upRate: 0, downRate: 0 }) }
      finally { polling = false }
    }
    void sample(); this.timer = setInterval(sample, 1000)
    let watching = false
    this.watchdog = setInterval(async () => {
      if (!current() || !this.session || watching) return
      watching = true
      try { const status = await this.helperRequest('/state'); if (status.phase === 'error') throw Error(status.error); helperFailures = 0 }
      catch { if (current() && ++helperFailures >= 3) void this.fail('Потеряна связь с VPN-службой') }
      finally { watching = false }
    }, 1500)
    void this.checkConnection(generation)
  }
  async checkConnection(generation = this.generation) {
    if (this.state.phase !== 'connected' || this.checking) return
    clearTimeout(this.healthTimer)
    this.checking = true; const controller = new AbortController(); this.healthController = controller
    const { checkHealth } = require('./health.cjs')
    try {
      const result = await checkHealth(this.prefs.httpPort, { signal: controller.signal })
      if (result && generation === this.generation && this.state.phase === 'connected') this.update(result)
    } finally {
      if (this.healthController === controller) { this.checking = false; this.healthController = null }
      if (generation === this.generation && this.state.phase === 'connected') this.healthTimer = setTimeout(() => this.checkConnection(generation), this.state.health === 'online' ? 12000 : 5000)
    }
  }
  recheck() {
    if (this.state.phase !== 'connected') return
    this.update({ health: 'checking', healthMessage: 'Повторная проверка доступа через сервер' })
    if (!this.checking) void this.checkConnection()
  }
  async fail(message) { await this.stop(); this.update({ error: message }) }
  async stop() {
    if (this.stopping) return this.stopping
    this.stopping = this.cleanup()
    try { await this.stopping } finally { this.stopping = null }
  }
  async cleanup() {
    ++this.generation; clearInterval(this.timer); clearInterval(this.watchdog); clearTimeout(this.healthTimer)
    this.healthController?.abort(); this.healthController = null; this.checking = false
    this.stats?.close(); this.stats = null
    this.update({ phase: 'disconnecting', stage: 'Восстановление настроек сети' })
    if (this.session) {
      await this.helperRequest('/stop', 'POST').catch(() => {})
      const end = Date.now() + 12000
      while (Date.now() < end) { try { await this.helperRequest('/state'); await delay(150) } catch { break } }
      this.session = null
    }
    if (this.child) {
      const child = this.child; this.child = null
      if (child.exitCode === null && child.pid) await exec('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true }).catch(() => {})
    }
    await this.recover().catch(e => this.update({ error: e.message }))
    if (this.configFile) { await fs.rm(this.configFile, { force: true }); this.configFile = null }
    this.update({ phase: 'disconnected', stage: '', health: 'unknown', since: 0, upRate: 0, downRate: 0 })
  }
}
module.exports = { Engine, listening }
