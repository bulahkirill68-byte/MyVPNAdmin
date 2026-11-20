const NAME = 'RealityVPN'
class Startup {
  constructor(app, { platform = process.platform, executable = process.execPath, portable = process.env.PORTABLE_EXECUTABLE_FILE } = {}) {
    this.app = app
    this.available = platform === 'win32' && app.isPackaged
    this.portable = Boolean(portable)
    // Use the original single-file launcher, not its versioned extraction cache.
    this.path = portable || executable
  }
  read() {
    if (!this.available) return { available: false, enabled: false, portable: this.portable, disabledByWindows: false }
    const settings = this.app.getLoginItemSettings({ path: this.path, args: [] })
    const disabledByWindows = settings.openAtLogin && !settings.executableWillLaunchAtLogin
    return { available: true, enabled: settings.openAtLogin && !disabledByWindows, portable: this.portable, disabledByWindows }
  }
  set(enabled) {
    if (typeof enabled !== 'boolean') throw Error('Некорректная настройка автозапуска')
    if (!this.available) throw Error('Автозапуск доступен в собранном Windows-приложении')
    this.app.setLoginItemSettings({ name: NAME, path: this.path, args: [], openAtLogin: enabled, enabled })
    const result = this.read()
    if (enabled && !result.enabled) throw Error('Не удалось включить автозапуск. Проверьте раздел «Автозагрузка» в Windows.')
    return result
  }
}
module.exports = { Startup }
