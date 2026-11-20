'use strict'
const { randomUUID } = require('node:crypto')
const net = require('node:net')
function parseVless(value) {
  if (typeof value !== 'string' || value.length > 4096) throw new Error('Ссылка слишком длинная')
  let url
  try { url = new URL(value.trim()) } catch { throw new Error('Вставьте корректную vless:// ссылку') }
  if (url.protocol !== 'vless:' || url.password) throw new Error('Поддерживаются VLESS-ссылки без пароля')
  const uuid = decodeURIComponent(url.username)
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(uuid)) throw new Error('Некорректный UUID')
  const host = url.hostname.replace(/^\[|\]$/g, '')
  if (!net.isIP(host) && !/^(?=.{1,253}$)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$/i.test(host)) throw new Error('Некорректный адрес сервера')
  const q = url.searchParams
  if (q.get('security') !== 'reality' || !['tcp', 'raw', null].includes(q.get('type'))) throw new Error('Нужен VLESS TCP + REALITY')
  if (q.has('flow') && q.get('flow') !== 'xtls-rprx-vision') throw new Error('Поддерживается только XTLS Vision')
  const publicKey = q.get('pbk') || ''
  const shortId = q.get('sid') || ''
  const sni = q.get('sni') || ''
  if (!/^[A-Za-z0-9_-]{43}$/.test(publicKey) || !/^(?:[a-f0-9]{2}){0,8}$/i.test(shortId)) throw new Error('Проверьте публичный ключ и Short ID')
  if (!/^(?=.{1,253}$)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$/i.test(sni)) throw new Error('Проверьте REALITY SNI')
  const fingerprint = q.get('fp') || 'firefox'
  if (!['firefox', 'chrome', 'safari', 'edge', 'randomized'].includes(fingerprint)) throw new Error('Неподдерживаемый fingerprint')
  const port = Number(url.port || 443)
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Некорректный порт')
  let name
  try { name = decodeURIComponent(url.hash.slice(1)) || host } catch { name = host }
  return { id: randomUUID(), name: name.slice(0, 80), host, port, uuid: uuid.toLowerCase(), publicKey, shortId, sni, fingerprint, uri: value.trim() }
}
function publicProfile(p) { return { id: p.id, name: p.name, host: p.host, port: p.port, sni: p.sni, fingerprint: p.fingerprint } }
module.exports = { parseVless, publicProfile }
