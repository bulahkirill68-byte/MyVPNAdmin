const fs = require('node:fs/promises')
const path = require('node:path')
const { safeStorage } = require('electron')
const { validatePrefs } = require('../shared/config.cjs')
class Store {
  constructor(directory) { this.directory = directory; this.file = path.join(directory, 'profiles.enc') }
  async load() {
    if (!safeStorage.isEncryptionAvailable()) throw Error('Windows encryption is unavailable')
    try { return JSON.parse(safeStorage.decryptString(await fs.readFile(this.file))) }
    catch (error) { if (error.code === 'ENOENT') return { profiles: [], selected: '', prefs: validatePrefs() }; throw Error('Не удалось расшифровать профили. Сохранённый файл не изменён.') }
  }
  async save(data) {
    if (!safeStorage.isEncryptionAvailable()) throw Error('Windows encryption is unavailable')
    await fs.mkdir(this.directory, { recursive: true })
    await fs.writeFile(this.file + '.tmp', safeStorage.encryptString(JSON.stringify(data)))
    await fs.rename(this.file + '.tmp', this.file)
  }
}
module.exports = { Store }
