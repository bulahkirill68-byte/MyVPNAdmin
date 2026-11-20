const { test } = require('node:test')
const assert = require('node:assert/strict')
const { Startup } = require('../electron/startup.cjs')
function fakeApp() {
  let registered = false, allowed = false
  const calls = []
  return {
    isPackaged: true, calls,
    getLoginItemSettings: options => { calls.push(['read', options]); return { openAtLogin: registered, executableWillLaunchAtLogin: allowed } },
    setLoginItemSettings: options => { calls.push(['write', options]); registered = options.openAtLogin; allowed = options.enabled },
    disableInWindows: () => { allowed = false }
  }
}
test('portable startup registers the original EXE and can be disabled', () => {
  const app = fakeApp(), original = 'C:\\My VPN\\RealityVPN-1.0.3-portable.exe'
  const startup = new Startup(app, { platform: 'win32', executable: 'C:\\cache\\Reality VPN.exe', portable: original })
  assert.equal(startup.read().enabled, false)
  assert.equal(startup.set(true).enabled, true)
  assert.deepEqual(app.calls.find(([method]) => method === 'write')[1], { name: 'RealityVPN', path: original, args: [], openAtLogin: true, enabled: true })
  assert.equal(startup.set(false).enabled, false)
})
test('installed app uses its executable and respects Windows disabling startup', () => {
  const app = fakeApp(), executable = 'C:\\Program Files\\Reality VPN\\Reality VPN.exe'
  const startup = new Startup(app, { platform: 'win32', executable, portable: '' })
  startup.set(true); app.disableInWindows()
  assert.equal(startup.read().enabled, false); assert.equal(startup.read().disabledByWindows, true)
  assert.equal(startup.set(true).enabled, true)
  assert.equal(app.calls.find(([method]) => method === 'write')[1].path, executable)
  assert.throws(() => startup.set('yes'))
})
test('development mode does not register Electron as a login item', () => {
  const app = fakeApp(); app.isPackaged = false
  const startup = new Startup(app, { platform: 'win32', portable: '' })
  assert.equal(startup.read().available, false)
  assert.throws(() => startup.set(true))
  assert.equal(app.calls.length, 0)
})
