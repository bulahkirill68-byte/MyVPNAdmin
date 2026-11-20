const { app, BrowserWindow, ipcMain, clipboard, dialog, powerMonitor } = require('electron')
const path = require('node:path')
const os = require('node:os')
const { Store } = require('./store.cjs')
const { Engine } = require('./engine.cjs')
const { parseVless, publicProfile } = require('../shared/profile.cjs')
const { validatePrefs } = require('../shared/config.cjs')
const { Startup } = require('./startup.cjs')
const helperIndex = process.argv.indexOf('--vpn-helper')
if (helperIndex !== -1) {
  app.whenReady().then(() => require('./helper.cjs').helper(process.argv[helperIndex + 1])).catch(() => app.exit(1))
} else if (!app.requestSingleInstanceLock()) app.quit()
else {
  let window, engine, data, store, operation, startup, startupState, busy = false, quitting = false
  const state = () => ({ profiles: data.profiles.map(publicProfile), selected: data.selected, prefs: data.prefs, startup: startupState, connection: { ...engine.state }, version: app.getVersion() })
  const notify = () => { if (window && !window.isDestroyed()) window.webContents.send('reality:state', state()) }
  const save = async () => { await store.save(data); notify(); return state() }
  function handle(name, fn, exclusive = false) {
    ipcMain.handle('reality:' + name, async (event, ...args) => {
      if (event.sender !== window.webContents || event.senderFrame !== window.webContents.mainFrame) throw Error('Untrusted sender')
      if (quitting) throw Error('Приложение закрывается')
      if (exclusive && busy) throw Error('Дождитесь завершения операции')
      if (exclusive) busy = true
      try { const result = fn(...args); if (exclusive) operation = Promise.resolve(result); return await result } finally { if (exclusive) { busy = false; operation = null } }
    })
  }
  app.whenReady().then(async () => {
    store = new Store(app.getPath('userData')); data = await store.load(); data.prefs = validatePrefs(data.prefs)
    engine = new Engine(app.getPath('userData'), notify)
    startup = new Startup(app); startupState = startup.read()
    handle('initial', state)
    handle('startup', () => { startupState = startup.read(); notify(); return state() })
    handle('setStartup', enabled => { startupState = startup.set(enabled); notify(); return state() }, true)
    handle('import', async uri => {
      const profile = parseVless(uri)
      const existing = data.profiles.find(p => p.uri === profile.uri)
      if (!existing) { if (data.profiles.length >= 100) throw Error('Максимум 100 профилей'); data.profiles.push(profile) }
      data.selected = existing?.id || profile.id; return save()
    }, true)
    handle('remove', async id => { if (engine.state.phase !== 'disconnected') throw Error('Сначала отключитесь'); data.profiles = data.profiles.filter(p => p.id !== id); if (data.selected === id) data.selected = data.profiles[0]?.id || ''; return save() }, true)
    handle('select', async id => { if (engine.state.phase !== 'disconnected') throw Error('Сначала отключитесь'); if (!data.profiles.some(p => p.id === id)) throw Error('Профиль не найден'); data.selected = id; return save() }, true)
    handle('connect', async mode => { if (!['proxy', 'vpn'].includes(mode)) throw Error('Некорректный режим'); const profile = data.profiles.find(p => p.id === data.selected); if (!profile) throw Error('Импортируйте VLESS-ссылку'); await engine.start(profile, data.prefs, mode); return state() }, true)
    handle('disconnect', async () => { await engine.stop(); return state() }, true)
    handle('recheck', () => { engine.recheck(); return state() })
    handle('prefs', async prefs => { if (engine.state.phase !== 'disconnected') throw Error('Сначала отключитесь'); data.prefs = validatePrefs(prefs); return save() }, true)
    handle('interfaces', () => Object.entries(os.networkInterfaces()).filter(([, ips]) => ips.some(ip => !ip.internal)).map(([name]) => name))
    handle('clipboard', async () => (await clipboard.readText()).slice(0, 4096))
    handle('copyAccess', async id => { const p = data.profiles.find(p => p.id === id); if (p) await clipboard.writeText(p.uri) })
    handle('diagnostics', () => JSON.stringify({ version: app.getVersion(), platform: process.platform, connection: engine.state, prefs: data.prefs, profile: data.profiles.filter(p => p.id === data.selected).map(publicProfile) }, null, 2))
    handle('minimize', () => window.minimize()); handle('close', () => window.close())
    window = new BrowserWindow({ width: 1140, height: 800, minWidth: 880, minHeight: 680, frame: false, backgroundColor: '#10131c', title: 'Reality VPN', webPreferences: { preload: path.join(__dirname, 'preload.cjs'), contextIsolation: true, nodeIntegration: false, sandbox: true } })
    window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
    window.webContents.on('will-navigate', event => event.preventDefault())
    await window.loadFile(path.join(__dirname, '../dist/index.html'))
    engine.prepare().catch(error => engine.update({ error: error.message }))
    powerMonitor.on('resume', () => engine.recheck())
    app.on('second-instance', () => { if (window.isMinimized()) window.restore(); window.focus() })
  }).catch(error => { dialog.showErrorBox('Reality VPN', error.message); app.exit(1) })
  app.on('window-all-closed', () => app.quit())
  app.on('before-quit', event => {
    if (!quitting && engine) { event.preventDefault(); quitting = true; Promise.resolve(operation).catch(() => {}).then(() => engine.stop()).finally(() => app.quit()) }
  })
}
