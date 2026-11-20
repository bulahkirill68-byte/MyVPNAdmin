const { test } = require('node:test')
const assert = require('node:assert/strict')
const { parseVless, publicProfile } = require('../shared/profile.cjs')
const { buildConfig, validatePrefs } = require('../shared/config.cjs')
const uri = 'vless://12345678-1234-1234-1234-123456789abc@203.0.113.1:443?type=tcp&security=reality&pbk=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA&sid=aabb&sni=example.com&flow=xtls-rprx-vision#Test'
test('import preserves credentials, default firefox, and hides secrets from renderer DTO', () => {
  const p = parseVless(uri)
  assert.equal(p.fingerprint, 'firefox'); assert.equal(p.port, 443)
  assert.deepEqual(Object.keys(publicProfile(p)).sort(), ['fingerprint','host','id','name','port','sni'])
  assert.ok(!JSON.stringify(publicProfile(p)).includes(p.uuid))
})
test('reject incompatible security, transports, invalid keys and credential schemes', () => {
  for (const invalid of [uri.replace('reality','tls'), uri.replace('type=tcp','type=ws'), uri.replace('xtls-rprx-vision','other'), uri.replace('sid=aabb','sid=a'), uri.replace('sni=example.com','sni=bad/path'), uri.replace('vless://','https://'), uri.replace('pbk=AAAA','pbk=A')]) assert.throws(() => parseVless(invalid))
})
test('AI explicit proxy rules precede Russia bypass; DNS requests go through proxy', () => {
  const config = buildConfig(parseVless(uri), {}, 'proxy')
  assert.equal(config.inbounds.length, 2)
  assert.ok(config.inbounds.every(i => i.listen === '127.0.0.1'))
  assert.equal(config.outbounds[0].streamSettings.realitySettings.fingerprint, 'firefox')
  const rules = config.routing.rules
  assert.ok(rules.findIndex(r => r.domain?.includes('domain:openai.com')) < rules.findIndex(r => r.ip?.includes('geoip:ru')))
  assert.deepEqual(rules.find(r => r.inboundTag?.includes('dns-query')), { type: 'field', inboundTag: ['dns-query'], outboundTag: 'proxy' })
  assert.equal(rules.find(r => r.domain?.includes('full:cp.cloudflare.com')).outboundTag, 'proxy')
})
test('TUN-only Windows fields and DNS leak guard are controlled by preferences', () => {
  const tun = buildConfig(parseVless(uri), { strictDns: false, interface: 'Ethernet' }, 'vpn').inbounds[0]
  assert.equal(tun.protocol, 'tun'); assert.equal(tun.settings.autoOutboundsInterface, 'Ethernet')
  assert.deepEqual(tun.settings.autoSystemWfpBlockLeak, [])
  assert.throws(() => validatePrefs({ socksPort: 10809 }))
  assert.throws(() => validatePrefs({ directDomains: 'https://site.com' }))
  assert.throws(() => validatePrefs({ interface: 'Ethernet\ncommand' }))
})
