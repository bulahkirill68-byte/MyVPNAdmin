<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { Check, Download, RefreshCw, Server, ShieldCheck } from 'lucide-vue-next'
import { api } from '../api'

const props = defineProps<{ serverIp?: string }>()
const emit = defineEmits<{ imported: [] }>()
interface State {
  available: boolean; imported: boolean; installed?: boolean; config_exists?: boolean; reason?: string
  job?: { state: string; message?: string; operation?: string }
}
const state = ref<State>(), ip = ref(props.serverIp || ''), sni = ref('www.wikipedia.org')
const confirmed = ref(false), busy = ref(false), error = ref(''), message = ref('')
let timer: ReturnType<typeof setInterval>
async function refresh() { try { state.value = await api<State>('/setup') } catch (e) { error.value = (e as Error).message } }
onMounted(() => { refresh(); timer = setInterval(refresh, 5000) })
onBeforeUnmount(() => clearInterval(timer))
async function operate(operation: 'install' | 'prepare' | 'import') {
  busy.value = true; error.value = ''; message.value = ''
  try {
    const result = await api<{message?: string}>(`/setup/${operation}`, 'POST', { ip: ip.value, sni: sni.value, confirm: confirmed.value })
    message.value = result.message || 'Задача запущена. Статус обновляется автоматически.'
    await refresh()
    if (operation === 'import') emit('imported')
  } catch (e) { error.value = (e as Error).message } finally { busy.value = false }
}
</script>
<template>
  <section class="panel setup-panel">
    <div class="panel-heading"><div><h3><Server :size="18" /> Установка и подключение Xray</h3><p>Ядро работает на Ubuntu-хосте, панель управляет настройкой через локальный агент.</p></div><button class="icon-btn" aria-label="Проверить агент" @click="refresh"><RefreshCw :size="17" /></button></div>
    <div class="setup-body">
      <div v-if="!state" class="muted">Проверяем хостовый агент…</div>
      <div v-else-if="!state.available" class="info-note"><strong>Нужен одноразовый bootstrap на хосте</strong><p>{{ state.reason }}</p><code>sudo bash scripts/install_agent.sh</code><p>Новые установки панели подключают агент автоматически.</p></div>
      <template v-else>
        <p class="subtle-note"><ShieldCheck :size="16" /> {{ state.imported ? 'Сервер подключён к панели.' : state.installed ? 'Обнаружено установленное ядро. Ключи и UUID сохранятся.' : 'Чистый VPS: установим официальный Xray, VLESS + REALITY и локальный API.' }}</p>
        <form v-if="!state.imported" class="form-stack" @submit.prevent="operate(state?.installed ? 'prepare' : 'install')">
          <div class="setup-fields"><label>Публичный IPv4 VPS<input v-model="ip" required placeholder="111.222.33.44" maxlength="15" /></label><label v-if="!state.installed">REALITY target / SNI<input v-model="sni" required maxlength="253" placeholder="www.wikipedia.org" /></label></div>
          <label class="setup-confirm"><input v-model="confirmed" type="checkbox" required /><span>{{ state.installed ? 'Разрешаю добавить API, email и статистику. Если поля отсутствуют, Xray будет перезапущен один раз; UUID и REALITY-ключи сохранятся.' : 'Разрешаю установить Xray на TCP 443. На сервере нет другой конфигурации Xray и порт 443 свободен.' }}</span></label>
          <div class="inline-actions"><button class="primary" :disabled="busy || state.job?.state === 'running' || !confirmed"><Download :size="17" /> {{ state.installed ? 'Подготовить существующий Xray' : 'Установить Xray + REALITY' }}</button><button v-if="state.config_exists" type="button" class="secondary" :disabled="busy || state.job?.state === 'running' || !confirmed" @click="operate('import')"><Check :size="17" /> Импортировать в панель</button></div>
        </form>
        <div v-if="state.job && state.job.state !== 'idle'" class="info-note" role="status"><strong>{{ ({running:'Настройка выполняется…',succeeded:'Готово',failed:'Ошибка настройки'} as Record<string,string>)[state.job.state] || state.job.state }}</strong><p>{{ state.job.message || 'Установка может занять несколько минут. Не запускайте вторую задачу.' }}</p><p v-if="state.job.state === 'succeeded' && !state.imported">Нажмите «Импортировать в панель», чтобы сохранить сервер и первый доступ.</p></div>
      </template>
      <p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="message" class="info-note" role="status">{{ message }}</p>
    </div>
  </section>
</template>
