export interface User {
  id: number
  name: string
  email: string
  comment: string
  expires_at: number | null
  quota_bytes: number | null
  used_bytes: number
  last_activity: number | null
  sync: string
  error: string | null
  policy: string
  status: string
  created: number
}
export interface Event {
  id: number
  at: number
  actor: string
  action: string
  user_id: number | null
  detail: string
}
export interface Rule {
  kind: 'domain' | 'ip'
  values: string[]
  outbound: 'direct' | 'proxy' | 'block'
}
export interface Routing {
  preset: string
  rules: Rule[]
  user_rules: Rule[]
  local_rules: Rule[]
}
export interface Traffic {
  at: number
  bytes: number
}
export interface Dashboard {
  worker: { ok: boolean; at?: number; stats?: boolean; uptime?: number; reason?: string; interval?: number }
  tcp443: boolean
  active: number
  total: number
  traffic: { day: number; month: number }
  resources: { cpu: number; ram: number; disk: number; disk_free: number }
  at: number
}
export interface Settings {
  server: { ip: string; port: number; sni: string; public_key: string; short_id: string; tag: string } | null
  backups: string[]
}
let csrf = ''
export function setCsrf(value: string) {
  csrf = value
}
export async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch('/api' + path, {
    method,
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const result = await response.json()
  if (!response.ok) {
    if (response.status === 401 && path !== '/login') window.dispatchEvent(new CustomEvent('session-expired'))
    throw new Error(typeof result.detail === 'string' ? result.detail : 'Проверьте поля формы')
  }
  return result
}
export function bytes(n: number | null | undefined) {
  if (n == null) return 'Безлимит'
  if (!n) return '0 Б'
  const i = Math.min(4, Math.floor(Math.log(n) / Math.log(1024)))
  return `${(n / 1024 ** i).toLocaleString('ru', { maximumFractionDigits: 1 })} ${['Б', 'КиБ', 'МиБ', 'ГиБ', 'ТиБ'][i]}`
}
export function date(n: number | null | undefined) {
  return n
    ? new Date(n * 1000).toLocaleString('ru', {
        timeZone: 'UTC',
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      }) + ' UTC'
    : 'Бессрочно'
}
export function download(name: string, data: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }))
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  URL.revokeObjectURL(url)
}
