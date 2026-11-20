const { execFile } = require('node:child_process')
const { promisify } = require('node:util')
const path = require('node:path')
const { app } = require('electron')
const exec = promisify(execFile)
function controlPath() { return path.join(app.isPackaged ? process.resourcesPath : path.join(__dirname, '../assets'), 'native/RuntimeControl.exe') }
async function control(args, timeout = 10000) {
  return (await exec(controlPath(), args, { windowsHide: true, timeout, maxBuffer: 1024 * 1024 })).stdout.trim()
}
async function readProxy() { return JSON.parse(await control(['proxy-read'])) }
async function setProxy(port) { await control(['proxy-set', String(port)]) }
async function restoreProxy(previous, port) { await control(['proxy-restore', String(port), Buffer.from(JSON.stringify(previous)).toString('base64')]) }
module.exports = { control, readProxy, setProxy, restoreProxy }
