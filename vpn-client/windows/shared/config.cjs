'use strict'
const RU = ['ru','su','xn--p1ai','ya.ru','yandex.com','yandex.net','yastatic.net','vk.com','vk.me','vkuser.net','userapi.com','mycdn.me','mail.ru','ok.ru','gosuslugi.ru','sber.ru','tbank.ru','tinkoff.ru','ozon.ru','ozonusercontent.com','wildberries.ru','wb.ru','wbbasket.ru']
const AI = ['chatgpt.com','openai.com','oaistatic.com','oaiusercontent.com','opencode.ai']
const DEFAULTS = { mode: 'proxy', ruDirect: true, interface: '', socksPort: 10808, httpPort: 10809, apiPort: 10915, manageProxy: true, strictDns: true, directDomains: '', proxyDomains: '', theme: 'dark' }
function validatePrefs(input = {}) {
  const p = { ...DEFAULTS }
  for (const k of ['ruDirect','manageProxy','strictDns']) if (typeof input[k] === 'boolean') p[k] = input[k]
  if (['proxy','vpn'].includes(input.mode)) p.mode = input.mode
  if (['dark','light'].includes(input.theme)) p.theme = input.theme
  for (const k of ['socksPort','httpPort','apiPort']) if (input[k] !== undefined) {
    if (!Number.isInteger(input[k]) || input[k] < 1024 || input[k] > 65535) throw new Error('Порты должны быть в диапазоне 1024–65535')
    p[k] = input[k]
  }
  if (new Set([p.socksPort,p.httpPort,p.apiPort]).size !== 3) throw new Error('Порты должны отличаться')
  if (input.interface !== undefined) {
    if (typeof input.interface !== 'string' || input.interface.length > 120 || /[\x00-\x1f]/.test(input.interface)) throw new Error('Некорректный интерфейс')
    p.interface = input.interface
  }
  for (const k of ['directDomains','proxyDomains']) if (input[k] !== undefined) {
    if (typeof input[k] !== 'string' || input[k].length > 4096) throw new Error('Слишком много доменных правил')
    const values = input[k].split(/[\s,;]+/).filter(Boolean)
    if (values.some(v => !/^[a-z0-9.-]+$/i.test(v))) throw new Error('В правилах нужны домены без URL и путей')
    p[k] = values.join('\n')
  }
  return p
}
function buildConfig(profile, settings, mode) {
  const p = validatePrefs(settings)
  const sniffing = { enabled: true, destOverride: ['http','tls','quic'], routeOnly: true }
  const inbounds = [
    {tag:'socks',listen:'127.0.0.1',port:p.socksPort,protocol:'socks',settings:{auth:'noauth',udp:true},sniffing},
    {tag:'http',listen:'127.0.0.1',port:p.httpPort,protocol:'http',settings:{},sniffing}
  ]
  if (mode === 'vpn') inbounds.unshift({tag:'tun',protocol:'tun',settings:{name:'RealityVPN',desc:'Reality VPN tunnel',mtu:1400,
    gateway:['172.28.64.1/30','fd66:7265:616c::1/126'],dns:['1.1.1.1'],autoSystemRoutingTable:['0.0.0.0/0','::/0'],
    autoOutboundsInterface:p.interface || 'auto',autoSystemWfpBlockLeak:p.strictDns ? ['dns'] : []},sniffing})
  const stream = { network:'tcp', security:'reality', realitySettings:{serverName:profile.sni,fingerprint:profile.fingerprint || 'firefox',
    publicKey:profile.publicKey,shortId:profile.shortId,spiderX:'/'} }
  if (p.interface) stream.sockopt = {interface:p.interface}
  const rules = [
    {type:'field',domain:['full:cp.cloudflare.com','full:www.gstatic.com'],outboundTag:'proxy'},
    {type:'field',inboundTag:['dns-query'],outboundTag:'proxy'},
    {type:'field',inboundTag:['tun','socks'],port:'53',outboundTag:'dns-out'},
    {type:'field',domain:[...AI,...p.proxyDomains.split('\n').filter(Boolean)].map(d=>'domain:'+d),outboundTag:'proxy'},
    {type:'field',ip:['geoip:private'],outboundTag:'direct'},
    {type:'field',domain:['full:localhost','domain:lan','domain:local','domain:home.arpa'],outboundTag:'direct'}
  ]
  if (p.directDomains) rules.push({type:'field',domain:p.directDomains.split('\n').map(d=>'domain:'+d),outboundTag:'direct'})
  if (p.ruDirect) rules.push({type:'field',domain:['geosite:category-ru',...RU.map(d=>'domain:'+d)],outboundTag:'direct'},
    {type:'field',ip:['geoip:ru'],outboundTag:'direct'})
  rules.push({type:'field',network:'tcp,udp',outboundTag:'proxy'})
  return {log:{loglevel:'warning'},stats:{},policy:{system:{statsOutboundUplink:true,statsOutboundDownlink:true}},
    api:{tag:'api',listen:`127.0.0.1:${p.apiPort}`,services:['StatsService']},
    dns:{tag:'dns-query',servers:['https://1.1.1.1/dns-query'],queryStrategy:'UseIPv4'},inbounds,
    outbounds:[{tag:'proxy',protocol:'vless',settings:{vnext:[{address:profile.host,port:profile.port,
      users:[{id:profile.uuid,encryption:'none',flow:'xtls-rprx-vision'}]}]},streamSettings:stream},
      {tag:'direct',protocol:'freedom',settings:{},streamSettings:{sockopt:{domainStrategy:'UseIP'}}},
      {tag:'dns-out',protocol:'dns',settings:{}},{tag:'block',protocol:'blackhole',settings:{}}],
    routing:{domainStrategy:'IPOnDemand',rules}}
}
module.exports = { DEFAULTS, validatePrefs, buildConfig, RU, AI }
