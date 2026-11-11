<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import {
  Activity,
  ArrowDownLeft,
  ArrowUpRight,
  Check,
  ChevronRight,
  Copy,
  Download,
  ExternalLink,
  Eye,
  Globe2,
  LayoutDashboard,
  LoaderCircle,
  LogOut,
  Menu,
  Moon,
  MoreHorizontal,
  Pause,
  Plus,
  RefreshCw,
  Search,
  Server,
  Settings2,
  Shield,
  ShieldCheck,
  Sun,
  Trash2,
  Users,
  X,
  Zap,
  GripVertical,
  ArrowUp,
  ArrowDown,
  FileClock,
  AlertCircle,
} from 'lucide-vue-next'
import QRCode from 'qrcode'
import TrafficChart from './components/TrafficChart.vue'
import Modal from './components/Modal.vue'
import RuleValues from './components/RuleValues.vue'
import SetupPanel from './components/SetupPanel.vue'
import {
  api,
  setCsrf,
  bytes,
  date,
  download,
  type User,
  type Event,
  type Dashboard,
  type Settings,
  type Traffic,
  type Routing,
  type Rule,
} from './api'
import { t } from './i18n'
const directHttps = window.location.protocol === 'https:'

const pages = [
  { id: 'dashboard', name: 'Обзор', icon: LayoutDashboard },
  { id: 'users', name: 'Пользователи', icon: Users },
  { id: 'routing', name: 'Маршрутизация', icon: Globe2 },
  { id: 'audit', name: 'Журнал событий', icon: FileClock },
  { id: 'settings', name: 'Настройки', icon: Settings2 },
]
const page = ref('dashboard'),
  mobile = ref(false),
  ready = ref(false),
  logged = ref(false),
  admin = ref('')
const loginName = ref(''),
  password = ref(''),
  busy = ref(false),
  error = ref(''),
  notice = ref('')
const userList = ref<User[]>([]),
  events = ref<Event[]>([]),
  stats = ref<Dashboard>(),
  traffic = ref<Traffic[]>([]),
  settings = ref<Settings>()
const routing = ref<Routing>({ preset: 'ru-direct', rules: [], user_rules: [], local_rules: [] })
const search = ref(''),
  filter = ref('all'),
  selected = ref<number[]>([])
const shownUsers = computed(() =>
  userList.value.filter(
    (u) =>
      (filter.value === 'all' || u.status === filter.value) &&
      (u.name + u.email + u.comment).toLowerCase().includes(search.value.toLowerCase()),
  ),
)
const theme = ref(localStorage.getItem('theme') || 'dark')
function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  localStorage.setItem('theme', theme.value)
  document.documentElement.dataset.theme = theme.value
}
let timer: ReturnType<typeof setInterval> | undefined, toastTimer: ReturnType<typeof setTimeout> | undefined
function toast(text: string) {
  notice.value = text
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => (notice.value = ''), 5000)
}
async function run(fn: () => Promise<void>) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    await fn()
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    busy.value = false
  }
}
async function load() {
  const [u, d, e, tr, s] = await Promise.all([
    api<User[]>('/users'),
    api<Dashboard>('/dashboard'),
    api<Event[]>('/audit'),
    api<Traffic[]>('/traffic'),
    api<Settings>('/settings'),
  ])
  userList.value = u
  stats.value = d
  events.value = e
  traffic.value = tr
  settings.value = s
  selected.value = selected.value.filter((id) => u.some((x) => x.id === id))
}
async function signIn() {
  await run(async () => {
    const data = await api<{ csrf: string }>('/login', 'POST', {
      name: loginName.value,
      password: password.value,
    })
    setCsrf(data.csrf)
    password.value = ''
    await init()
  })
}
async function init() {
  const me = await api<{ name: string; csrf: string }>('/me')
  admin.value = me.name
  setCsrf(me.csrf)
  await load()
  routing.value = await api<Routing>('/routing')
  logged.value = true
}
function expired() {
  logged.value = false
  setCsrf('')
}
async function logout() {
  await run(async () => {
    await api('/logout', 'POST')
    logged.value = false
    userList.value = []
    access.value = null
    detail.value = null
  })
}
onMounted(async () => {
  document.documentElement.dataset.theme = theme.value
  window.addEventListener('session-expired', expired)
  try {
    await init()
  } catch {
    /* Login screen */
  }
  ready.value = true
  timer = setInterval(() => {
    if (logged.value && !busy.value) load().catch((e) => (error.value = e.message))
  }, 15000)
})
onBeforeUnmount(() => {
  clearInterval(timer)
  clearTimeout(toastTimer)
  window.removeEventListener('session-expired', expired)
})

const editor = ref(false),
  editId = ref<number | null>(null),
  step = ref(1)
const form = ref({ name: '', comment: '', term: '30', customDate: '', quota: '', policy: 'ru-direct' })
function openEditor(user?: User) {
  editId.value = user?.id ?? null
  step.value = 1
  form.value = {
    name: user?.name ?? '',
    comment: user?.comment ?? '',
    term: user?.expires_at ? 'custom' : user ? 'forever' : '30',
    customDate: user?.expires_at ? new Date(user.expires_at * 1000).toISOString().slice(0, 16) : '',
    quota: user?.quota_bytes ? String(user.quota_bytes / 1024 ** 3) : '',
    policy: user?.policy ?? 'ru-direct',
  }
  detail.value = null
  editor.value = true
}
async function saveUser() {
  await run(async () => {
    const f = form.value
    const expires =
      f.term === 'forever'
        ? null
        : f.term === 'custom'
          ? Math.floor(Date.parse(f.customDate + 'Z') / 1000)
          : Math.floor(Date.now() / 1000) + Number(f.term) * 86400
    if (expires !== null && !Number.isFinite(expires)) throw new Error('Укажите дату UTC')
    const body = {
      name: f.name.trim(),
      comment: f.comment,
      expires_at: expires,
      quota_bytes: f.quota ? Math.round(Number(f.quota) * 1024 ** 3) : null,
      policy: f.policy,
    }
    const user = await api<User>(
      editId.value ? `/users/${editId.value}` : '/users',
      editId.value ? 'PUT' : 'POST',
      body,
    )
    editor.value = false
    await load()
    if (!editId.value) await showAccess(user)
    else toast('Изменения сохранены; ожидается применение в Xray')
  })
}
const detail = ref<User | null>(null),
  detailTraffic = ref<Traffic[]>([]),
  detailEvents = ref<Event[]>([])
async function showDetail(user: User) {
  await run(async () => {
    detail.value = user
    detailTraffic.value = await api<Traffic[]>(`/traffic?user_id=${user.id}`)
    detailEvents.value = await api<Event[]>(`/audit?user_id=${user.id}`)
  })
}
const access = ref<{
    uuid: string
    link: string
    qr: string
    status: string
    name: string
    id: number
  } | null>(null),
  reveal = ref(false),
  subUrl = ref('')
async function showAccess(user: User) {
  const value = await api<{ uuid: string; link: string; status: string }>(`/users/${user.id}/access`)
  access.value = {
    ...value,
    qr: await QRCode.toDataURL(value.link, { width: 300, margin: 2, errorCorrectionLevel: 'M' }),
    name: user.name,
    id: user.id,
  }
  reveal.value = false
  subUrl.value = ''
  detail.value = null
}
async function copy(value: string) {
  try {
    await navigator.clipboard.writeText(value)
    toast('Скопировано')
  } catch {
    error.value = 'Буфер обмена недоступен. Выделите и скопируйте вручную.'
  }
}
async function subscription() {
  if (!access.value) return
  await run(async () => {
    const value = await api<{ url: string }>(`/users/${access.value!.id}/actions`, 'POST', {
      action: 'token',
    })
    subUrl.value = value.url
  })
}
async function revokeToken() {
  if (!access.value) return
  await run(async () => {
    await api(`/users/${access.value!.id}/actions`, 'POST', { action: 'revoke_token' })
    subUrl.value = ''
    toast('Токен отозван')
  })
}
async function exportUserRouting() {
  if (!access.value) return
  await run(async () => {
    download('v2rayNG-user-routing.json', await api(`/users/${access.value!.id}/routing/export`))
  })
}
async function exportClientConfig() {
  if (!access.value) return
  await run(async () => download('reality-client-config.json', await api(`/users/${access.value!.id}/client-config`)))
}
const confirmation = ref<{ ids: number[]; action: string; title: string } | null>(null)
function confirmAction(ids: number[], action: string) {
  confirmation.value = {
    ids,
    action,
    title: (
      {
        pause: 'Приостановить доступ?',
        resume: 'Возобновить доступ?',
        revoke: 'Аннулировать доступ?',
        delete: 'Удалить пользователя?',
        rotate: 'Заменить UUID?',
      } as Record<string, string>
    )[action],
  }
  detail.value = null
}
async function applyAction() {
  if (!confirmation.value) return
  await run(async () => {
    const c = confirmation.value!
    for (const id of c.ids) await api(`/users/${id}/actions`, 'POST', { action: c.action, confirm: true })
    confirmation.value = null
    selected.value = []
    await load()
    toast('Сохранено. Статус применения обновит worker.')
  })
}
const renewUser = ref<User | null>(null),
  renewDays = ref(30),
  renewMode = ref('expiry'),
  renewPreview = ref<number | null>(null)
function openRenew(user: User) {
  renewUser.value = user
  renewPreview.value = null
  detail.value = null
}
async function previewRenew() {
  await run(async () => {
    const p = await api<{ expires_at: number }>(
      `/users/${renewUser.value!.id}/renew-preview?days=${renewDays.value}&mode=${renewMode.value}`,
    )
    renewPreview.value = p.expires_at
  })
}
async function applyRenew() {
  await run(async () => {
    await api(`/users/${renewUser.value!.id}/actions`, 'POST', {
      action: 'renew',
      days: renewDays.value,
      mode: renewMode.value,
      expected_expires: renewPreview.value,
    })
    renewUser.value = null
    await load()
    toast('Срок продлён')
  })
}
const routeScope = ref<'rules' | 'user_rules' | 'local_rules'>('rules'),
  routeTarget = ref(''),
  routeResult = ref(''),
  dragIndex = ref<number | null>(null)
const routeRules = computed(() => routing.value[routeScope.value])
function moveRule(from: number, to: number) {
  if (to < 0 || to >= routeRules.value.length) return
  const [item] = routeRules.value.splice(from, 1)
  routeRules.value.splice(to, 0, item)
}
function dropRule(to: number) {
  if (dragIndex.value !== null) moveRule(dragIndex.value, to)
  dragIndex.value = null
}
async function saveRouting() {
  await run(async () => {
    await api('/routing', 'PUT', routing.value)
    toast('Профиль сохранён. Экспортируйте и импортируйте его в клиент.')
  })
}
async function exportRouting() {
  await run(async () => {
    await api('/routing', 'PUT', routing.value)
    download('v2rayNG-routing.json', await api('/routing/export'))
  })
}
async function importRouting(event: globalThis.Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  await run(async () => {
    if (file.size > 131072) throw new Error('Файл слишком большой')
    const json = JSON.parse(await file.text())
    const rules = json.rules ?? json.routing?.rules
    if (!Array.isArray(rules)) throw new Error('Нужен объект routing с массивом rules')
    routing.value.rules = rules
      .filter((r: Record<string, unknown>) => r.domain || r.ip)
      .map((r: Record<string, unknown>): Rule => {
        if (r.domain && r.ip) throw new Error('Разделите domain и IP на отдельные правила')
        if (!['proxy', 'direct', 'block'].includes(String(r.outboundTag)))
          throw new Error('Допустимы теги proxy/direct/block')
        return {
          kind: r.domain ? 'domain' : 'ip',
          values: (r.domain || r.ip) as string[],
          outbound: r.outboundTag as Rule['outbound'],
        }
      })
    routing.value.preset = 'custom'
    toast('Импортировано в редактор. Проверьте порядок и сохраните.')
  })
  input.value = ''
}
async function testRouting() {
  await run(async () => {
    await api('/routing', 'PUT', routing.value)
    const r = await api<{ outbound: string; rule: number; note: string; approximate: boolean }>(
      `/routing/test?target=${encodeURIComponent(routeTarget.value)}`,
    )
    routeResult.value = `${r.outbound ?? 'Нет данных'} · правило ${r.rule ?? '—'}. ${r.note}`
  })
}
const showServerSecrets = ref(false)
function navigate(id: string) {
  page.value = id
  mobile.value = false
}
function closeAccess() {
  access.value = null
  subUrl.value = ''
}
const serverLabels: Record<string, string> = {
  ip: 'Публичный IPv4',
  port: 'Порт',
  sni: 'REALITY SNI',
  public_key: 'Публичный ключ',
  short_id: 'Short ID',
  tag: 'Inbound tag',
}
async function backup() {
  await run(async () => {
    const r = await api<{ name: string }>('/backup', 'POST')
    toast(`Создана копия ${r.name}`)
    await load()
  })
}
const uptime = computed(() =>
  stats.value?.worker.uptime == null
    ? 'Нет данных'
    : `${Math.floor(stats.value.worker.uptime / 86400)}д ${Math.floor(stats.value.worker.uptime / 3600) % 24}ч`,
)
const workerFresh = computed(() => !!stats.value?.worker.at && Date.now() / 1000 - stats.value.worker.at < 60)
function ratio(user: User) {
  return user.quota_bytes ? Math.min(100, (user.used_bytes / user.quota_bytes) * 100) : 0
}
</script>

<template>
  <div v-if="!ready" class="boot">
    <Shield :size="44" /><span>REALITY CONTROL</span><LoaderCircle class="spin" />
  </div>
  <main v-else-if="!logged" class="login-screen">
    <div class="login-art">
      <div class="brand">
        <div class="brand-icon"><Shield :size="24" /></div>
        reality<span>control</span>
      </div>
      <div class="login-orbit"><ShieldCheck :size="74" /></div>
      <h1>Ваш сервер.<br />Полный контроль.</h1>
      <p>Управляйте доступом, следите за трафиком<br />и держите инфраструктуру под контролем.</p>
      <span class="secure-tag"><ShieldCheck :size="15" /> {{ directHttps ? 'Защищённая панель · HTTPS' : 'Приватная панель · SSH tunnel' }}</span>
    </div>
    <form class="login-card" @submit.prevent="signIn">
      <span class="eyebrow">ДОБРО ПОЖАЛОВАТЬ</span>
      <h2>Вход в панель</h2>
      <p class="muted">Защищённое пространство администратора</p>
      <label
        >Имя администратора<input
          v-model="loginName"
          autocomplete="username"
          required
          autofocus
          placeholder="Введите имя"
          maxlength="80" /></label
      ><label
        >Пароль<input
          v-model="password"
          type="password"
          autocomplete="current-password"
          required
          maxlength="256"
          placeholder="Ваш пароль"
      /></label>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <button class="primary full" :disabled="busy">
        <LoaderCircle v-if="busy" class="spin" :size="18" /><span>Войти в панель</span
        ><ArrowUpRight :size="18" />
      </button>
      <p class="login-help">
        <ShieldCheck :size="15" /> {{ directHttps ? 'Защищённое HTTPS-подключение.' : 'Доступ только через localhost.' }}<br />Первый администратор создаётся командой
        CLI.
      </p>
    </form>
  </main>
  <div v-else class="app-shell">
    <div v-if="mobile" class="nav-backdrop" @click="mobile = false" />
    <aside class="sidebar" :class="{ open: mobile }">
      <a
        href="#"
        class="brand"
        @click.prevent="navigate('dashboard')"
        ><div class="brand-icon"><Shield :size="23" /></div>
        <div>reality<span>control</span></div></a
      >
      <div class="workspace">
        <span class="server-symbol"><Server :size="18" /></span>
        <div>
          <strong>Мой VPS</strong><small>{{ settings?.server?.ip ?? 'Ожидает импорта' }}</small>
        </div>
        <span class="live-dot" :class="{ off: !stats?.worker.ok }" />
      </div>
      <div class="nav-caption">УПРАВЛЕНИЕ</div>
      <nav aria-label="Основная навигация">
        <button
          v-for="item in pages"
          :key="item.id"
          :class="{ active: page === item.id }"
          @click="navigate(item.id)"
        >
          <component :is="item.icon" :size="19" /><span>{{ item.name }}</span
          ><span v-if="item.id === 'users'" class="nav-count">{{ userList.length }}</span>
        </button>
      </nav>
      <div class="sidebar-bottom">
        <div class="connection">
          <span class="live-dot" :class="{ off: !stats?.worker.ok }" />
          <div>
            <strong>{{ stats?.worker.ok ? 'Xray подключён' : 'Нет синхронизации' }}</strong
            ><small>Локальный gRPC · 10085</small>
          </div>
        </div>
        <div class="admin">
          <div class="avatar">{{ admin[0]?.toUpperCase() }}</div>
          <div>
            <strong>{{ admin }}</strong
            ><small>Владелец сервера</small>
          </div>
          <button class="icon-btn" aria-label="Выйти" @click="logout"><LogOut :size="17" /></button>
        </div>
      </div>
    </aside>
    <div class="main-column">
      <header class="topbar">
        <div class="breadcrumb">
          <button class="icon-btn mobile-only" aria-label="Меню" @click="mobile = true">
            <Menu :size="21" /></button
          ><span>Рабочее пространство</span><ChevronRight :size="14" /><strong>{{
            pages.find((p) => p.id === page)?.name
          }}</strong>
        </div>
        <div class="top-actions">
          <span class="tunnel"><ShieldCheck :size="14" /> {{ directHttps ? 'HTTPS · защищено' : 'SSH · защищено' }}</span
          ><button
            class="icon-btn"
            :aria-label="theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'"
            @click="toggleTheme"
          >
            <Sun v-if="theme === 'dark'" :size="19" /><Moon v-else :size="19" /></button
          ><button class="icon-btn" aria-label="Обновить данные" :disabled="busy" @click="run(load)">
            <RefreshCw :size="17" :class="{ spin: busy }" />
          </button>
        </div>
      </header>
      <main class="content" :key="page">
        <div v-if="error" class="banner danger" role="alert">
          <AlertCircle :size="19" /><span>{{ error }}</span
          ><button class="icon-btn" aria-label="Скрыть ошибку" @click="error = ''"><X :size="16" /></button>
        </div>
        <template v-if="page === 'dashboard'">
          <div class="page-heading">
            <div>
              <span class="eyebrow">ВАША ИНФРАСТРУКТУРА, В ОДНОМ МЕСТЕ</span>
              <h1>Обзор сервера<span class="heading-dot">.</span></h1>
              <p>Всё, что нужно знать о вашем VPN прямо сейчас.</p>
            </div>
            <button class="primary" @click="openEditor()"><Plus :size="18" /> Добавить пользователя</button>
          </div>
          <div v-if="!settings?.server" class="banner">
            <ShieldCheck :size="23" />
            <div>
              <strong>Подключите действующий сервер</strong>
              <p>Выполните безопасный импорт по инструкции README. Конфигурация и ключи Xray сохранятся.</p>
            </div>
            <button class="secondary" @click="page = 'settings'">
              Инструкция <ChevronRight :size="16" />
            </button>
          </div>
          <section class="server-hero">
            <div class="hero-grid" />
            <div class="hero-status">
              <div class="hero-icon"><Server :size="28" /></div>
              <div>
                <span class="eyebrow">XRAY · VLESS REALITY</span>
                <h2>{{ settings?.server?.ip ?? 'Сервер ещё не импортирован' }}</h2>
                <p>XTLS Vision <span>•</span> {{ settings?.server?.sni ?? 'SNI появится после импорта' }}</p>
              </div>
            </div>
            <div class="hero-info">
              <span class="badge" :class="stats?.worker.ok ? 'active' : 'paused'"
                ><span class="live-dot" :class="{ off: !stats?.worker.ok }" />{{
                  stats?.worker.ok ? 'Работает' : 'Нет данных / ошибка'
                }}</span
              >
              <div>
                <span>Порт TCP 443</span
                ><strong>{{ stats?.tcp443 ? 'Доступен локально' : 'Не отвечает' }}</strong>
              </div>
              <div>
                <span>Uptime Xray</span><strong>{{ workerFresh ? uptime : 'Нет данных' }}</strong>
              </div>
            </div>
          </section>
          <section class="metric-grid">
            <article class="metric">
              <div class="metric-top"><span>Активные пользователи</span><Users :size="19" /></div>
              <div class="metric-value">
                {{ stats?.active ?? '—' }}<small>/ {{ stats?.total ?? '—' }}</small>
              </div>
              <span class="metric-foot"><span class="live-dot" /> По сроку и условиям доступа</span>
            </article>
            <article class="metric">
              <div class="metric-top"><span>Трафик сегодня</span><ArrowUpRight :size="19" /></div>
              <div class="metric-value">
                {{ stats?.worker.stats ? bytes(stats.traffic.day) : 'Нет данных' }}
              </div>
              <span class="metric-foot">Входящий + исходящий · UTC</span>
            </article>
            <article class="metric">
              <div class="metric-top"><span>Трафик за месяц</span><ArrowDownLeft :size="19" /></div>
              <div class="metric-value">
                {{ stats?.worker.stats ? bytes(stats.traffic.month) : 'Нет данных' }}
              </div>
              <span class="metric-foot">С момента установки панели</span>
            </article>
            <article class="metric">
              <div class="metric-top"><span>Синхронизация</span><Activity :size="19" /></div>
              <div class="metric-value compact">{{ stats?.worker.ok ? 'В норме' : 'Нет данных' }}</div>
              <span class="metric-foot">{{
                stats?.worker.reason ??
                (stats?.worker.at
                  ? 'Обновлено ' + new Date(stats.worker.at * 1000).toLocaleTimeString('ru')
                  : 'Ожидается worker')
              }}</span>
            </article>
          </section>
          <div class="dashboard-grid">
            <section class="panel traffic-panel">
              <div class="panel-heading">
                <div>
                  <h3>Трафик сервера</h3>
                  <p>Фактическое потребление пользователей</p>
                </div>
                <span class="chip">Последние 7 дней</span>
              </div>
              <TrafficChart :data="traffic" />
              <div class="chart-footer">
                <span><i /> Входящий + исходящий</span><span>Почасовая агрегация · UTC</span>
              </div>
            </section>
            <section class="panel resources">
              <div class="panel-heading">
                <h3>Ресурсы VPS</h3>
                <Activity :size="18" />
              </div>
              <div
                v-for="(label, key) in {
                  cpu: 'Процессор',
                  ram: 'Оперативная память',
                  disk: 'Хранилище /data',
                }"
                :key="key"
                class="resource"
              >
                <div>
                  <span>{{ label }}</span
                  ><strong>{{ stats?.resources[key]?.toFixed(1) ?? '—' }}<small>%</small></strong>
                </div>
                <div class="progress"><i :style="{ width: (stats?.resources[key] ?? 0) + '%' }" /></div>
              </div>
              <div class="resource-note">
                <ShieldCheck :size="17" />
                <p>
                  Данные ОС и файловой системы.<br />{{ bytes(stats?.resources.disk_free) }} свободно на
                  /data.
                </p>
              </div>
            </section>
          </div>
          <div class="dashboard-grid">
            <section class="panel">
              <div class="panel-heading">
                <div>
                  <h3>Последние события</h3>
                  <p>Прозрачная история изменений</p>
                </div>
                <button class="text-btn" @click="page = 'audit'">
                  Все события <ArrowUpRight :size="16" />
                </button>
              </div>
              <div v-if="!events.length" class="empty">Пока нет событий</div>
              <div v-for="event in events.slice(0, 5)" :key="event.id" class="event-row">
                <div class="event-icon"><Activity :size="16" /></div>
                <div>
                  <strong>{{ event.action === 'applied' ? t('applied_action') : t(event.action) }}</strong
                  ><small
                    >{{ event.actor }}{{ event.user_id ? ' · Пользователь #' + event.user_id : '' }}
                    {{ event.detail }}</small
                  >
                </div>
                <time>{{
                  new Date(event.at * 1000).toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit' })
                }}</time>
              </div>
            </section>
            <section class="quick-card">
              <div class="quick-icon"><Zap :size="24" /></div>
              <h3>Доступ за пару кликов</h3>
              <p>
                Создайте пользователя, задайте срок и квоту. Поделитесь персональной ссылкой или QR-кодом.
              </p>
              <button class="secondary full" @click="openEditor()">Создать доступ <Plus :size="17" /></button
              ><button class="text-btn" @click="page = 'routing'">
                Настроить маршрутизацию <ArrowUpRight :size="15" />
              </button>
            </section>
          </div>
        </template>

        <template v-if="page === 'users'">
          <div class="page-heading">
            <div>
              <span class="eyebrow">ДОСТУП ПОД КОНТРОЛЕМ</span>
              <h1>Пользователи<span class="heading-dot">.</span></h1>
              <p>Персональный доступ. Понятные сроки. Гибкие лимиты.</p>
            </div>
            <button class="primary" @click="openEditor()"><Plus :size="18" /> Добавить пользователя</button>
          </div>
          <section class="panel">
            <div class="table-toolbar">
              <div class="search">
                <Search :size="17" /><input
                  v-model="search"
                  aria-label="Поиск пользователей"
                  placeholder="Найти по имени, email, комментарию…"
                />
              </div>
              <select v-model="filter" aria-label="Фильтр статуса">
                <option value="all">Все статусы</option>
                <option
                  v-for="state in ['active', 'paused', 'expired', 'quota_exceeded', 'revoked']"
                  :key="state"
                  :value="state"
                >
                  {{ t(state) }}
                </option>
              </select>
            </div>
            <div v-if="selected.length" class="bulk">
              <strong>Выбрано: {{ selected.length }}</strong
              ><button class="secondary" @click="confirmAction(selected, 'pause')">
                <Pause :size="15" /> Приостановить</button
              ><button class="secondary" @click="confirmAction(selected, 'resume')">Возобновить</button
              ><button class="danger-btn" @click="confirmAction(selected, 'delete')">Удалить</button>
            </div>
            <div class="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>
                      <input
                        type="checkbox"
                        aria-label="Выбрать всех видимых"
                        :checked="!!shownUsers.length && shownUsers.every((u) => selected.includes(u.id))"
                        @change="
                          selected = ($event.target as HTMLInputElement).checked
                            ? shownUsers.map((u) => u.id)
                            : []
                        "
                      />
                    </th>
                    <th>Пользователь</th>
                    <th>Статус</th>
                    <th>Действует до</th>
                    <th>Трафик</th>
                    <th>Применение</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="user in shownUsers" :key="user.id">
                    <td>
                      <input
                        v-model="selected"
                        type="checkbox"
                        :value="user.id"
                        :aria-label="'Выбрать ' + user.name"
                      />
                    </td>
                    <td>
                      <button class="user-cell" @click="showDetail(user)">
                        <span class="avatar">{{ user.name[0]?.toUpperCase() }}</span
                        ><span
                          ><strong>{{ user.name }}</strong
                          ><small>{{ user.email }}</small></span
                        >
                      </button>
                    </td>
                    <td>
                      <span class="badge" :class="user.status">{{ t(user.status) }}</span>
                    </td>
                    <td class="date-cell">{{ date(user.expires_at) }}</td>
                    <td class="quota-cell">
                      <div>
                        {{ bytes(user.used_bytes) }} <span>/ {{ bytes(user.quota_bytes) }}</span>
                      </div>
                      <div v-if="user.quota_bytes" class="progress" :class="{ warning: ratio(user) >= 80 }">
                        <i :style="{ width: ratio(user) + '%' }" />
                      </div>
                      <small v-if="user.quota_bytes"
                        >Осталось {{ bytes(Math.max(0, user.quota_bytes - user.used_bytes)) }}</small
                      >
                    </td>
                    <td>
                      <span class="sync" :class="user.sync" :title="user.error ?? ''"
                        ><Check v-if="user.sync === 'applied'" :size="13" /><RefreshCw v-else :size="13" />{{
                          t(user.sync)
                        }}</span
                      >
                    </td>
                    <td>
                      <button class="icon-btn" :aria-label="'Открыть ' + user.name" @click="showDetail(user)">
                        <MoreHorizontal :size="20" />
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-if="!shownUsers.length" class="empty">
              <Users :size="32" />
              <h3>{{ userList.length ? 'Ничего не найдено' : 'Ваш первый пользователь' }}</h3>
              <p>
                {{
                  userList.length
                    ? 'Попробуйте изменить поисковый запрос.'
                    : 'Импортируйте существующий доступ или создайте новый после подключения сервера.'
                }}
              </p>
              <button v-if="!userList.length" class="secondary" @click="openEditor()">
                <Plus :size="16" /> Создать пользователя
              </button>
            </div>
            <div class="table-footer">
              {{ shownUsers.length }} пользователей · Одно устройство = отдельный UUID и квота
            </div>
          </section>
          <p class="subtle-note">
            <ShieldCheck :size="15" /> Пауза и блокировка прекращают допуск новых подключений. Уже открытые
            сессии могут сохраняться.
          </p>
        </template>

        <template v-if="page === 'routing'">
          <div class="page-heading">
            <div>
              <span class="eyebrow">ПРАВИЛЬНЫЙ МАРШРУТ</span>
              <h1>Маршрутизация<span class="heading-dot">.</span></h1>
              <p>Раздельное туннелирование для ваших клиентов.</p>
            </div>
            <button class="primary" :disabled="busy" @click="saveRouting">
              <Check :size="17" /> Сохранить профиль
            </button>
          </div>
          <div class="banner">
            <Globe2 :size="23" />
            <div>
              <strong>Правила применяются в клиентском приложении</strong>
              <p>
                Обычная VLESS-подписка обновляет узлы. Маршрутизация импортируется отдельно, исключения
                Android-приложений настраиваются вручную.
              </p>
            </div>
          </div>
          <div class="preset-grid">
            <button
              v-for="preset in [
                {
                  id: 'ru-direct',
                  title: 'Россия напрямую',
                  desc: 'Локальные сети и RU — direct. Остальное — VPN.',
                  icon: Globe2,
                },
                {
                  id: 'all-proxy',
                  title: 'Всё через VPN',
                  desc: 'Все TCP/UDP подключения через прокси.',
                  icon: Shield,
                },
                {
                  id: 'custom',
                  title: 'Пользовательский',
                  desc: 'Свои правила перед стандартной политикой.',
                  icon: Settings2,
                },
              ]"
              :key="preset.id"
              class="preset"
              :class="{ chosen: routing.preset === preset.id }"
              @click="routing.preset = preset.id"
            >
              <component :is="preset.icon" :size="24" /><strong>{{ preset.title }}</strong
              ><span>{{ preset.desc }}</span
              ><Check v-if="routing.preset === preset.id" class="preset-check" :size="17" />
            </button>
          </div>
          <section class="panel">
            <div class="panel-heading">
              <div>
                <h3>Приоритетные правила</h3>
                <p>Первое совпадение определяет маршрут. Перетаскивайте или используйте стрелки.</p>
              </div>
              <button
                class="secondary"
                @click="
                  routeRules.push({ kind: 'domain', values: ['domain:example.com'], outbound: 'proxy' })
                "
              >
                <Plus :size="16" /> Правило
              </button>
            </div>
            <div class="scope-tabs">
              <button
                v-for="s in [
                  { id: 'rules', label: 'Политика администратора' },
                  { id: 'user_rules', label: 'Политика пользователя · шаблон' },
                  { id: 'local_rules', label: 'Локальные исключения' },
                ]"
                :key="s.id"
                :class="{ active: routeScope === s.id }"
                @click="routeScope = s.id as typeof routeScope"
              >
                {{ s.label }}
              </button>
            </div>
            <div class="rules">
              <div
                v-for="(rule, index) in routeRules"
                :key="index"
                class="rule"
                draggable="true"
                @dragstart="dragIndex = index"
                @dragover.prevent
                @drop.prevent="dropRule(index)"
              >
                <GripVertical :size="17" /><span class="rule-number">{{ index + 1 }}</span>
                <select v-model="rule.kind" aria-label="Тип критерия">
                  <option value="domain">Домен</option>
                  <option value="ip">IP / CIDR</option>
                </select>
                <RuleValues v-model="rule.values" />
                <select v-model="rule.outbound" aria-label="Маршрут">
                  <option>proxy</option>
                  <option>direct</option>
                  <option>block</option>
                </select>
                <button class="icon-btn" aria-label="Выше" @click="moveRule(index, index - 1)">
                  <ArrowUp :size="15" /></button
                ><button class="icon-btn" aria-label="Ниже" @click="moveRule(index, index + 1)">
                  <ArrowDown :size="15" /></button
                ><button class="icon-btn" aria-label="Удалить правило" @click="routeRules.splice(index, 1)">
                  <Trash2 :size="16" />
                </button>
              </div>
              <div v-if="!routeRules.length" class="empty small">
                Нет дополнительных правил. Используется выбранный пресет.
              </div>
            </div>
            <div class="routing-baseline">
              <h4>Стандартный порядок · {{ routing.preset === 'all-proxy' ? 'VPN' : 'Россия напрямую' }}</h4>
              <p v-if="routing.preset !== 'all-proxy'">
                Исключения proxy → private IP → localhost / .lan / .local / home.arpa → российские домены →
                geoip:ru → остальное proxy.
              </p>
              <p v-else>Дополнительные правила → остальное TCP/UDP proxy.</p>
              <small
                >Локальные исключения имеют приоритет над индивидуальной и глобальной политикой. Нужны
                актуальные geoip/geosite клиента.</small
              >
            </div>
            <div class="panel-actions">
              <button class="secondary" @click="exportRouting">
                <Download :size="16" /> Экспорт v2rayNG JSON</button
              ><label class="secondary file-label"
                ><ArrowUpRight :size="16" /> Импорт JSON<input
                  type="file"
                  accept=".json,application/json"
                  @change="importRouting"
              /></label>
            </div>
          </section>
          <section class="panel route-test">
            <div>
              <h3>Проверить маршрут</h3>
              <p>Предварительный результат без локальной базы GeoIP/GeoSite.</p>
            </div>
            <form @submit.prevent="testRouting">
              <input
                v-model="routeTarget"
                required
                maxlength="253"
                placeholder="Домен или IP-адрес"
                aria-label="Домен или IP для проверки"
              /><button class="secondary" :disabled="busy">Проверить <ArrowUpRight :size="16" /></button>
            </form>
            <p v-if="routeResult" class="test-result">{{ routeResult }}</p>
          </section>
          <section class="panel prose">
            <h3>Как применить в v2rayNG</h3>
            <ol>
              <li>Экспортируйте JSON и передайте его по приватному каналу.</li>
              <li>
                Откройте настройки маршрутизации клиента. В версиях с импортом Xray routing импортируйте
                объект rules; если ваша версия ожидает собственный формат, перенесите правила в редактор
                вручную в указанном порядке.
              </li>
              <li>
                Проверьте теги proxy/direct/block, обновите geoip.dat и geosite.dat. Включите IPOnDemand и
                sniffing при необходимости.
              </li>
              <li>
                Android: в Per-app proxy отдельно выберите приложения. Подписка не изменяет этот список.
              </li>
            </ol>
          </section>
        </template>

        <template v-if="page === 'audit'"
          ><div class="page-heading">
            <div>
              <span class="eyebrow">ПРОЗРАЧНОСТЬ И КОНТРОЛЬ</span>
              <h1>Журнал событий<span class="heading-dot">.</span></h1>
              <p>Последние 200 событий доступа, управления и worker.</p>
            </div>
          </div>
          <section class="panel">
            <div v-for="event in events" :key="event.id" class="event-row">
              <div class="event-icon"><Activity :size="17" /></div>
              <div>
                <strong>{{ event.action === 'applied' ? t('applied_action') : t(event.action) }}</strong
                ><small
                  >{{ event.actor }}{{ event.user_id ? ' · #' + event.user_id : '' }} ·
                  {{ event.detail || '—' }}</small
                >
              </div>
              <time>{{ date(event.at) }}</time>
            </div>
            <div v-if="!events.length" class="empty">Пока нет событий</div>
          </section></template
        >

        <template v-if="page === 'settings'">
          <SetupPanel :server-ip="settings?.server?.ip" @imported="run(load)" />
          <div class="page-heading">
            <div>
              <span class="eyebrow">ОСНОВА ВАШЕЙ СЕТИ</span>
              <h1>Настройки сервера<span class="heading-dot">.</span></h1>
              <p>Параметры подключения и обслуживание панели.</p>
            </div>
            <span class="chip"><Server :size="15" /> Один VPS</span>
          </div>
          <div class="settings-grid">
            <section class="panel settings-panel">
              <div class="panel-heading">
                <h3>VLESS + REALITY</h3>
                <button class="text-btn" @click="showServerSecrets = !showServerSecrets">
                  <Eye :size="15" /> {{ showServerSecrets ? 'Скрыть' : 'Показать параметры' }}
                </button>
              </div>
              <template v-if="settings?.server"
                ><dl>
                  <div v-for="(value, key) in settings.server" :key="key">
                    <dt>{{ serverLabels[key] }}</dt>
                    <dd>
                      {{
                        ['public_key', 'short_id'].includes(key) && !showServerSecrets
                          ? '••••••••••••••••'
                          : value
                      }}
                    </dd>
                  </div>
                </dl>
                <p class="subtle-note">
                  <ShieldCheck :size="17" /> Приватный REALITY-ключ хранится только на хосте. Глобальные
                  параметры доступны для чтения.
                </p></template
              >
              <div v-else class="empty">Выполните импорт по инструкции ниже.</div>
            </section>
            <section class="panel settings-panel">
              <div class="panel-heading">
                <h3>Резервные копии</h3>
                <ShieldCheck :size="18" />
              </div>
              <p class="muted">
                Автоматически раз в сутки. Храним последние 14 копий SQLite с проверкой целостности.
              </p>
              <button class="secondary full" :disabled="busy" @click="backup">
                <Download :size="17" /> Создать копию сейчас
              </button>
              <ul class="backup-list">
                <li v-for="name in settings?.backups?.slice(0, 5)" :key="name">
                  <FileClock :size="15" /> {{ name }}
                </li>
              </ul>
              <p class="subtle-note">
                Восстановление — через SSH с остановкой web и worker. Команда: bash scripts/restore.sh
                ИМЯ_КОПИИ
              </p>
            </section>
          </div>
          <section class="panel prose">
            <h3>Первоначальное подключение</h3>
            <p>
              На VPS создайте администратора и импортируйте разрешённые метаданные существующего конфига.
              Публичный ключ возьмите из /root/xray-reality-access-*.txt. UUID и ключи не меняются.
            </p>
            <pre>
docker compose exec web python -m app.cli admin
python3 scripts/export_xray.py --ip ВАШ_IP --public-key ПУБЛИЧНЫЙ_КЛЮЧ \
  | docker compose exec -T web python -m app.cli import</pre>
            <h4>Диагностика и обслуживание</h4>
            <pre>
bash scripts/diagnose.sh
docker compose logs --tail=100 worker
bash scripts/backup.sh</pre>
            <p>
              Обновление: bash scripts/update.sh. Конфиг Xray и служба на хосте не изменяются. Все инструкции
              — в README и docs/DEPLOYMENT_RU.md.
            </p>
          </section>
        </template>
        <footer class="page-footer">
          <span>reality control <span class="version">v0.2</span></span
          ><span>{{ directHttps ? 'HTTPS-панель' : 'Локальная панель' }} · Ваш сервер, ваши данные</span>
        </footer>
      </main>
    </div>
  </div>

  <Modal
    v-if="editor"
    :title="editId ? 'Изменить пользователя' : 'Новый пользователь'"
    @close="editor = false"
    ><form @submit.prevent="step === 1 ? (step = 2) : saveUser()">
      <div class="wizard-steps">
        <span :class="{ current: step === 1 }">01 · Пользователь</span><i /><span
          :class="{ current: step === 2 }"
          >02 · Условия доступа</span
        >
      </div>
      <div v-if="step === 1" class="form-stack">
        <label
          >Имя / устройство<input
            v-model="form.name"
            required
            maxlength="100"
            placeholder="Например, Анна · Android"
            autofocus /></label
        ><label
          >Комментарий<textarea
            v-model="form.comment"
            maxlength="2000"
            rows="3"
            placeholder="Только для администратора"
          />
        </label>
        <p class="info-note">
          Для каждого устройства создаётся отдельный UUID. Жёсткое ограничение одновременных устройств не
          применяется.
        </p>
      </div>
      <div v-else class="form-stack">
        <label
          >Срок доступа<select v-model="form.term">
            <option value="forever">Бессрочно</option>
            <option v-for="days in [1, 7, 30, 90]" :key="days" :value="String(days)">{{ days }} дней</option>
            <option value="custom">Точная дата / время UTC</option>
          </select></label
        ><label v-if="form.term === 'custom'"
          >Дата и время UTC<input v-model="form.customDate" type="datetime-local" required /></label
        ><label
          >Квота трафика, ГиБ<input
            v-model="form.quota"
            type="number"
            min="0.01"
            step="0.01"
            max="9000000"
            placeholder="Пусто = безлимит"
        /></label>
        <div class="quota-presets">
          <button v-for="q in [5, 10, 30, 50, 100]" :key="q" type="button" @click="form.quota = String(q)">
            {{ q }} ГиБ</button
          ><button type="button" @click="form.quota = ''">∞</button>
        </div>
        <label
          >Профиль маршрутизации<select v-model="form.policy">
            <option value="ru-direct">Россия напрямую</option>
            <option value="all-proxy">Всё через VPN</option>
            <option value="custom">Пользовательский</option>
          </select></label
        >
        <p class="info-note">
          Профиль — назначение для отдельного экспорта правил, VLESS-ссылка не меняет настройки клиента.
          Трафик считается uplink + downlink.
        </p>
      </div>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <div class="modal-actions">
        <button v-if="step === 2" type="button" class="secondary" @click="step = 1">Назад</button
        ><button v-else type="button" class="secondary" @click="editor = false">Отмена</button
        ><button class="primary" :disabled="busy">
          {{ step === 1 ? 'Продолжить' : editId ? 'Сохранить' : 'Создать доступ' }}<ChevronRight :size="17" />
        </button>
      </div></form
  ></Modal>

  <Modal v-if="detail" :title="detail.name" wide @close="detail = null"
    ><div class="detail-top">
      <span class="badge" :class="detail.status">{{ t(detail.status) }}</span
      ><span class="sync" :class="detail.sync">{{ t(detail.sync) }}</span>
    </div>
    <p v-if="detail.error" class="error">{{ detail.error }}</p>
    <p class="muted">{{ detail.comment || 'Без комментария' }}</p>
    <div class="detail-metrics">
      <div>
        <small>Действует до</small><strong>{{ date(detail.expires_at) }}</strong>
      </div>
      <div>
        <small>Израсходовано / квота</small
        ><strong>{{ bytes(detail.used_bytes) }} / {{ bytes(detail.quota_bytes) }}</strong>
      </div>
      <div>
        <small>Последний замеченный трафик</small
        ><strong>{{ detail.last_activity ? date(detail.last_activity) : 'Нет данных' }}</strong>
      </div>
    </div>
    <div class="progress quota-large" :class="{ warning: ratio(detail) >= 80 }">
      <i :style="{ width: ratio(detail) + '%' }" />
    </div>
    <div class="detail-actions">
      <button class="primary" @click="run(() => showAccess(detail!))">
        <Eye :size="16" /> Карточка доступа</button
      ><button class="secondary" @click="openRenew(detail)"><Plus :size="16" /> Продлить</button
      ><button class="secondary" @click="openEditor(detail)"><Settings2 :size="16" /> Изменить</button
      ><button
        class="secondary"
        @click="
          confirmAction(
            [detail.id],
            detail.status === 'paused' || detail.status === 'revoked' ? 'resume' : 'pause',
          )
        "
      >
        {{ detail.status === 'paused' || detail.status === 'revoked' ? 'Возобновить' : 'Приостановить' }}
      </button>
    </div>
    <TrafficChart :data="detailTraffic" />
    <div class="detail-log">
      <h4>История пользователя</h4>
      <div v-for="e in detailEvents.slice(0, 12)" :key="e.id" class="event-row">
        <div>
          <strong>{{ e.action === 'applied' ? t('applied_action') : t(e.action) }}</strong
          ><small>{{ e.detail }}</small>
        </div>
        <time>{{ date(e.at) }}</time>
      </div>
    </div>
    <div class="modal-actions">
      <button class="danger-btn" @click="confirmAction([detail.id], 'delete')">
        <Trash2 :size="15" /> Удалить
      </button>
      <div class="inline-actions">
        <button class="text-btn" @click="confirmAction([detail.id], 'revoke')">Аннулировать</button
        ><button class="secondary" @click="confirmAction([detail.id], 'rotate')">Заменить UUID</button>
      </div>
    </div></Modal
  >

  <Modal
    v-if="access"
    title="Карточка доступа"
    @close="closeAccess"
  >
    <button class="text-btn" @click="exportUserRouting">
      <Download :size="15" /> Экспорт назначенного профиля маршрутизации
    </button>
    <button class="primary full" @click="exportClientConfig"><Download :size="17" /> Клиентский JSON с маршрутизацией</button>
    <p class="info-note">Профиль по умолчанию: Россия напрямую. Импортируйте полный JSON как custom configuration в совместимый клиент. Обычный QR/VLESS ниже содержит только узел. Android Per-app proxy настраивается отдельно.</p>
    <div class="access-head">
      <span class="success-circle"><Check :size="24" /></span>
      <h3>{{ access.name }}</h3>
      <p>Персональный доступ · VLESS + REALITY</p>
      <span class="badge" :class="access.status">{{ t(access.status) }}</span>
    </div>
    <div class="qr-wrap">
      <img v-if="reveal" :src="access.qr" alt="QR-код подключения VLESS" width="240" height="240" />
      <div v-else class="qr-hidden">
        <ShieldCheck :size="38" />
        <p>Данные доступа скрыты</p>
        <button class="secondary" @click="reveal = true">Показать QR и ссылку</button>
      </div>
    </div>
    <template v-if="reveal"
      ><label
        >UUID
        <div class="copy-field">
          <input :value="access.uuid" readonly aria-label="UUID" /><button
            type="button"
            class="icon-btn"
            aria-label="Копировать UUID"
            @click="copy(access.uuid)"
          >
            <Copy :size="17" />
          </button></div></label
      ><label
        >VLESS-ссылка
        <div class="copy-field">
          <input :value="access.link" readonly aria-label="VLESS-ссылка" /><button
            class="icon-btn"
            aria-label="Копировать ссылку"
            @click="copy(access.link)"
          >
            <Copy :size="17" />
          </button></div></label
      ><button class="primary full" @click="copy(access.link)">
        <Copy :size="17" /> Скопировать ссылку
      </button></template
    >
    <details class="subscription">
      <summary>Локальная подписка через SSH</summary>
      <p>
        URL работает только на localhost через туннель. Для автообновления на телефоне нужен достижимый HTTPS
        URL с действительным сертификатом; MVP его не публикует.
      </p>
      <button class="secondary" @click="subscription">
        {{ subUrl ? 'Заменить токен' : 'Создать токен' }}</button
      ><button class="text-btn" @click="revokeToken">Отозвать токен</button>
      <div v-if="subUrl" class="copy-field">
        <input :value="subUrl" readonly aria-label="Локальная подписка" /><button
          class="icon-btn"
          aria-label="Копировать URL"
          @click="copy(subUrl)"
        >
          <Copy :size="16" />
        </button>
      </div>
    </details>
    <p class="info-note">
      Передавайте ссылку приватно. Статус фактического применения смотрите в таблице пользователей.
    </p>
    <div class="modal-actions">
      <button
        class="secondary"
        @click="closeAccess"
      >
        Готово
      </button>
    </div>
  </Modal>

  <Modal v-if="confirmation" :title="confirmation.title" @close="confirmation = null"
    ><p class="muted">
      Пользователей: {{ confirmation.ids.length }}. Изменение будет передано worker и применено через Xray
      API.
    </p>
    <p v-if="confirmation.action === 'rotate'" class="info-note">
      Старая VLESS-ссылка перестанет работать. REALITY-ключ сервера сохранится.
    </p>
    <p v-if="['pause', 'revoke', 'delete'].includes(confirmation.action)" class="info-note">
      Новые подключения будут отклоняться после применения. Мгновенный разрыв существующих соединений не
      гарантируется.
    </p>
    <p v-if="error" class="error">{{ error }}</p>
    <div class="modal-actions">
      <button class="secondary" @click="confirmation = null">Отмена</button
      ><button class="primary" :disabled="busy" @click="applyAction">Подтвердить</button>
    </div></Modal
  >

  <Modal v-if="renewUser" title="Продлить доступ" @close="renewUser = null"
    ><p class="muted">{{ renewUser.name }} · Сейчас: {{ date(renewUser.expires_at) }}</p>
    <div class="form-stack">
      <label
        >Количество дней<input
          v-model.number="renewDays"
          type="number"
          min="1"
          max="3650"
          @input="renewPreview = null" /></label
      ><label
        >Как считать срок<select v-model="renewMode" @change="renewPreview = null">
          <option value="expiry">От срока окончания, если он не истёк</option>
          <option value="now">От текущей даты</option>
        </select></label
      ><button class="secondary" :disabled="busy" @click="previewRenew">Рассчитать итоговую дату</button>
      <div v-if="renewPreview" class="renew-result">
        <small>Новый срок UTC</small><strong>{{ date(renewPreview) }}</strong>
      </div>
    </div>
    <p v-if="error" class="error">{{ error }}</p>
    <div class="modal-actions">
      <button class="secondary" @click="renewUser = null">Отмена</button
      ><button class="primary" :disabled="!renewPreview || busy" @click="applyRenew">
        Подтвердить продление
      </button>
    </div></Modal
  >
  <Transition name="toast"
    ><div v-if="notice" class="toast" role="status">
      <span><Check :size="17" /></span>{{ notice }}
    </div></Transition
  >
</template>
