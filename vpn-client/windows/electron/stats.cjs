// Loaded only when connecting, not while opening the window or in the elevated helper.
function varint(n) { const bytes = []; do { bytes.push((n & 127) | (n > 127 ? 128 : 0)); n >>>= 7 } while (n); return Buffer.from(bytes) }
function encodeString(value) { const b = Buffer.from(value); return Buffer.concat([Buffer.from([10]), varint(b.length), b]) }
function number(buffer, position) { let n = 0n, shift = 0n; for (let i = 0; i < 10; i++) { if (position.i >= buffer.length) throw Error('Invalid protobuf'); const b = buffer[position.i++]; n |= BigInt(b & 127) << shift; if (!(b & 128)) return n; shift += 7n } throw Error('Invalid varint') }
function skip(buffer, p, wire) {
  if (wire === 0) number(buffer, p)
  else if (wire === 1) p.i += 8
  else if (wire === 2) { const size = Number(number(buffer, p)); p.i += size }
  else if (wire === 5) p.i += 4
  else throw Error('Unsupported protobuf wire type')
  if (p.i > buffer.length) throw Error('Truncated protobuf')
}
function decode(buffer) {
  const p = { i: 0 }, stats = []
  while (p.i < buffer.length) {
    const key = Number(number(buffer, p))
    if (key !== 10) { skip(buffer, p, key & 7); continue }
    const size = Number(number(buffer, p)), end = p.i + size
    if (end > buffer.length) throw Error('Invalid stats size')
    const item = buffer.subarray(p.i, end), cursor = { i: 0 }; p.i = end
    let name = '', value = 0
    while (cursor.i < item.length) {
      const tag = Number(number(item, cursor))
      if (tag === 10) { const length = Number(number(item, cursor)); if (cursor.i + length > item.length) throw Error('Invalid stat name'); name = item.subarray(cursor.i, cursor.i + length).toString(); cursor.i += length }
      else if (tag === 16) value = Number(number(item, cursor))
      else skip(item, cursor, tag & 7)
    }
    stats.push({ name, value })
  }
  return stats
}
class StatsReader {
  constructor(port) {
    const grpc = require('@grpc/grpc-js')
    const Client = grpc.makeGenericClientConstructor({ query: { path: '/xray.app.stats.command.StatsService/QueryStats', requestStream: false, responseStream: false, requestSerialize: () => encodeString('outbound>>>proxy>>>traffic>>>'), responseDeserialize: decode } }, 'Stats')
    this.client = new Client(`127.0.0.1:${port}`, grpc.credentials.createInsecure(), { 'grpc.initial_reconnect_backoff_ms': 100, 'grpc.min_reconnect_backoff_ms': 100, 'grpc.max_reconnect_backoff_ms': 1000 })
  }
  read() { return new Promise((resolve, reject) => this.client.query({}, { deadline: Date.now() + 1200 }, (e, stats) => e ? reject(e) : resolve(stats))) }
  close() { this.client.close() }
}
class TrafficTracker {
  constructor() { this.previous = {}; this.totals = { up: 0, down: 0 }; this.time = 0 }
  sample(stats, time = Date.now()) {
    const seconds = this.time ? Math.max(.1, (time - this.time) / 1000) : 0, delta = { up: 0, down: 0 }
    for (const [direction, suffix] of [['up', 'uplink'], ['down', 'downlink']]) {
      const stat = stats.find(s => s.name === `outbound>>>proxy>>>traffic>>>${suffix}`)
      if (!stat || !Number.isFinite(stat.value) || stat.value < 0) continue
      const previous = this.previous[direction]
      delta[direction] = previous === undefined || stat.value < previous ? stat.value : stat.value - previous
      this.totals[direction] += delta[direction]; this.previous[direction] = stat.value
    }
    this.time = time
    return { ...this.totals, upRate: seconds ? delta.up / seconds : 0, downRate: seconds ? delta.down / seconds : 0, statsAt: time, statsStatus: 'ready' }
  }
}
module.exports = { StatsReader, TrafficTracker, decode, encodeString }
