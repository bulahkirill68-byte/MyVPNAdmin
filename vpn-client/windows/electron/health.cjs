const https = require('node:https')
const { HttpsProxyAgent } = require('https-proxy-agent')
const TARGETS = ['https://cp.cloudflare.com/generate_204', 'https://www.gstatic.com/generate_204']
function requestProbe(url, agent, signal) {
  return new Promise((resolve, reject) => {
    const start = performance.now()
    const request = https.get(url, { agent, signal, headers: { 'User-Agent': 'RealityVPN/connectivity', 'Cache-Control': 'no-cache' } }, response => {
      response.resume()
      // A redirected/captive-portal HTTP 200 is not connectivity success.
      if (response.statusCode === 204) resolve(Math.round(performance.now() - start))
      else reject(Error('Unexpected connectivity response'))
    })
    request.on('error', reject)
  })
}
async function checkHealth(port, { signal, request = requestProbe, timeout = 4500 } = {}) {
  const controller = new AbortController()
  const abort = () => controller.abort()
  if (signal?.aborted) controller.abort(); else signal?.addEventListener('abort', abort, { once: true })
  const timer = setTimeout(abort, timeout)
  const agent = new HttpsProxyAgent(`http://127.0.0.1:${port}`, { keepAlive: false })
  const started = Date.now()
  try {
    const latency = await Promise.any(TARGETS.map(url => request(url, agent, controller.signal)))
    return { health: 'online', latency, checkedAt: Date.now(), lastOnline: Date.now(), healthMessage: 'Доступ через VPN подтверждён' }
  } catch {
    if (signal?.aborted) return null
    return { health: 'degraded', latency: null, checkedAt: Date.now(), healthMessage: 'Нет ответа через VPN. Сервер или проверочные адреса недоступны в этой сети.', probeMs: Date.now() - started }
  } finally { clearTimeout(timer); controller.abort(); signal?.removeEventListener('abort', abort); agent.destroy() }
}
module.exports = { checkHealth, TARGETS }
