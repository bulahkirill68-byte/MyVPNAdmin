<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Check, Download, RefreshCw, Server, ShieldCheck } from 'lucide-vue-next'
import { api } from '../api'

const props = defineProps<{ serverIp?: string }>()
const emit = defineEmits<{ imported: [] }>()
interface State {
  available: boolean
  imported: boolean
  installed?: boolean
  config_exists?: boolean
  has_managed_inbound?: boolean
  can_initialize?: boolean
  configuration?: string
  reason?: string
  public_ip?: string
  job?: { state: string; message?: string; operation?: string }
}
type Operation = 'install' | 'initialize' | 'prepare'
const state = ref<State>()
const ip = ref(props.serverIp || '')
const sni = ref('www.wikipedia.org')
const confirmed = ref(false)
const busy = ref(false)
const error = ref('')
const message = ref('')
let jobSubmitted = false
let ipInitialized = Boolean(props.serverIp)
let timer: ReturnType<typeof setInterval>
const action = computed<Operation | ''>(() => {
  if (!state.value) return ''
  if (state.value.can_initialize) return 'initialize'
  if (state.value.installed && state.value.has_managed_inbound !== false) return 'prepare'
  if (!state.value.installed && !state.value.config_exists) return 'install'
  return ''
})
const actionLabel = computed(() => ({ install: 'Установить Xray + REALITY',
  initialize: 'Завершить настройку VLESS + REALITY', prepare: 'Подготовить существующий Xray' })[action.value || 'install'])
const canImport = computed(() => state.value?.config_exists && state.value?.has_managed_inbound !== false)
const running = computed(() => busy.value || state.value?.job?.state === 'running')
const jobLabels: Record<string, string> = { running: 'Настройка выполняется…', succeeded: 'Готово', failed: 'Ошибка настройки' }

async function refresh() {
  try {
    state.value = await api<State>('/setup')
    if (jobSubmitted && ['succeeded', 'failed'].includes(state.value.job?.state || '')) {
      message.value = ''
      jobSubmitted = false
    }
    if (!ipInitialized && state.value.public_ip) {
      if (!ip.value) ip.value = state.value.public_ip
      ipInitialized = true
    }
  } catch (e) { error.value = (e as Error).message }
}
onMounted(() => { refresh(); timer = setInterval(refresh, 5000) })
onBeforeUnmount(() => clearInterval(timer))
async function operate(operation: Operation | 'import' | '') {
  if (!operation) return
  busy.value = true; error.value = ''; message.value = ''
  try {
    const result = await api<{ message?: string }>(`/setup/${operation}`, 'POST', {
      ip: ip.value, sni: sni.value, confirm: confirmed.value,
    })
    message.value = result.message || 'Задача запущена. Статус обновляется автоматически.'
    jobSubmitted = operation !== 'import'
    await refresh()
    if (operation === 'import') emit('imported')
  } catch (e) { error.value = (e as Error).message } finally { busy.value = false }
}
</script>
<template>
  <section class="panel setup-panel">
    <div class="panel-heading">
      <div><h3><Server :size="18" /> Установка и подключение Xray</h3><p>Ядро работает на Ubuntu-хосте, настройка — через локальный агент.</p></div>
      <button class="icon-btn" aria-label="Проверить агент" @click="refresh"><RefreshCw :size="17" /></button>
    </div>
    <div class="setup-body">
      <div v-if="!state" class="muted">Проверяем хостовый агент…</div>
      <div v-else-if="!state.available" class="info-note">
        <strong>Нужен одноразовый bootstrap на хосте</strong><p>{{ state.reason }}</p>
        <code>sudo bash scripts/install_agent.sh</code><p>Новые установки панели подключают агент автоматически.</p>
      </div>
      <template v-else>
        <p class="subtle-note"><ShieldCheck :size="16" />
          {{ state.imported ? 'Сервер подключён к панели.' : action === 'initialize'
            ? 'Бинарник Xray найден, но VLESS + REALITY ещё не настроен. Можно безопасно завершить пустую установку.'
            : action === 'prepare' ? 'Обнаружен VLESS + REALITY inbound. UUID и ключи сохранятся.'
            : action === 'install' ? 'Чистый VPS: установим официальный Xray, VLESS + REALITY и локальный API.'
            : state.reason || 'Нужна ручная проверка существующей конфигурации.' }}
        </p>
        <form v-if="!state.imported && action" class="form-stack" @submit.prevent="operate(action)">
          <div class="setup-fields">
            <label>Публичный IPv4 VPS<input v-model="ip" required placeholder="111.222.33.44" maxlength="15" /></label>
            <label v-if="action !== 'prepare'">REALITY target / SNI<input v-model="sni" required maxlength="253" placeholder="www.wikipedia.org" /></label>
          </div>
          <label class="setup-confirm"><input v-model="confirmed" type="checkbox" required /><span>
            {{ action === 'prepare'
              ? 'Разрешаю добавить API, email и статистику. При изменении конфигурации Xray перезапустится один раз; UUID и ключи сохранятся.'
              : action === 'initialize'
              ? 'Разрешаю создать VLESS + REALITY в отсутствующем или пустом конфиге и разрешить TCP 443 в активном UFW. Непустой конфиг и существующие пользователи не заменяются.'
              : 'Разрешаю установить Xray и разрешить TCP 443 в активном UFW. На сервере нет другой конфигурации Xray и порт 443 свободен.' }}
          </span></label>
          <div class="inline-actions">
            <button class="primary" :disabled="running || !confirmed"><Download :size="17" /> {{ actionLabel }}</button>
            <button v-if="canImport" type="button" class="secondary" :disabled="running || !confirmed" @click="operate('import')"><Check :size="17" /> Импортировать в панель</button>
          </div>
        </form>
        <div v-if="!state.imported && !action" class="info-note">
          {{ state.reason || 'Конфигурация требует ручной проверки. Автоматическая замена отключена.' }}
        </div>
        <div v-if="state.job && state.job.state !== 'idle'" class="info-note" role="status">
          <strong>{{ jobLabels[state.job.state] || state.job.state }}</strong>
          <p>{{ state.job.message || 'Установка может занять несколько минут. Не запускайте вторую задачу.' }}</p>
          <p v-if="state.job.state === 'succeeded' && !state.imported && canImport">Нажмите «Импортировать в панель», чтобы сохранить сервер и первый доступ.</p>
        </div>
      </template>
      <p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="message" class="info-note" role="status">{{ message }}</p>
    </div>
  </section>
</template>
