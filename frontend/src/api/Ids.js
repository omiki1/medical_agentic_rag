/**
 * 本地幂等标识生成。
 *
 * 为什么不能直接用 crypto.randomUUID()：
 * 它只在"安全上下文"（Secure Context）可用 —— HTTPS 或 localhost。
 * 本项目部署在 http://47.83.165.114:8010（纯 HTTP + 公网 IP），
 * 属于非安全上下文，crypto.randomUUID 为 undefined，直接调用抛
 * `TypeError: crypto.randomUUID is not a function`。
 * 后果不是"报个错"这么轻：它在 send() 里位于 busy=true 之后、try 之前，
 * 一抛异常 busy 就永久卡在 true，发送按钮变停止按钮，整个界面卡死。
 * 而本地用 localhost 开发时永远复现不出来。
 *
 * 回退顺序：
 *   1. crypto.randomUUID（安全上下文，最标准）
 *   2. crypto.getRandomValues（不受安全上下文限制，仍是密码学随机）
 *   3. Math.random（极端环境兜底；仅用于本地幂等标识，不承担安全用途）
 *
 * cryptoObject 可注入，便于测试非安全上下文；生产调用不传参，用全局 crypto。
 */
export function uuid(cryptoObject = globalThis.crypto) {
  if (typeof cryptoObject?.randomUUID === 'function') return cryptoObject.randomUUID()

  const bytes = new Uint8Array(16)
  if (typeof cryptoObject?.getRandomValues === 'function') cryptoObject.getRandomValues(bytes)
  else for (let i = 0; i < 16; i += 1) bytes[i] = Math.floor(Math.random() * 256)

  bytes[6] = (bytes[6] & 0x0f) | 0x40 // version 4
  bytes[8] = (bytes[8] & 0x3f) | 0x80 // variant 10xx
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
