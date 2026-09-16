export class SSEDecoder {
  constructor() { this.buffer = '' }
  feed(text, final = false) {
    this.buffer += text
    if (this.buffer.length > 2_000_000) throw new Error('服务返回的数据过大')
    const frames = this.buffer.split(/\r?\n\r?\n/)
    this.buffer = frames.pop()
    if (final && this.buffer.trim()) throw new Error('数据流意外中断，请恢复历史记录')
    return frames.flatMap(frame => {
      const data = frame.split(/\r?\n/).filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n')
      return data ? [JSON.parse(data)] : []
    })
  }
}

class ApiClient {
  csrf = ''
  async request(path, options = {}) {
    const headers = { ...options.headers }
    if (options.body) headers['Content-Type'] = 'application/json'
    if (this.csrf) headers['X-MediAtlas-CSRF'] = this.csrf
    const response = await fetch(path, { credentials: 'same-origin', ...options, headers })
    if (!response.ok) {
      if (response.status === 401) globalThis.dispatchEvent?.(new Event('mediatlas:unauthorized'))
      const error = await response.json().catch(() => ({}))
      throw new Error(typeof error.detail === 'string' ? error.detail : `请求失败（${response.status}）`)
    }
    return response.json()
  }
  async session() {
    const session = await this.request('/api/session')
    this.csrf = session.csrf
    return session
  }
  get(path) { return this.request(path) }
  post(path, data) { return this.request(path, { method: 'POST', body: data === undefined ? undefined : JSON.stringify(data) }) }
  patch(path, data) { return this.request(path, { method: 'PATCH', body: JSON.stringify(data) }) }
  delete(path) { return this.request(path, { method: 'DELETE' }) }
  async *chat(payload, signal) {
    const response = await fetch('/api/chat', { method: 'POST', signal, credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-MediAtlas-CSRF': this.csrf }, body: JSON.stringify(payload) })
    if (!response.ok) {
      if (response.status === 401) globalThis.dispatchEvent?.(new Event('mediatlas:unauthorized'))
      const error = await response.json().catch(() => ({}))
      throw new Error(typeof error.detail === 'string' ? error.detail : `请求失败（${response.status}）`)
    }
    if (!response.body) throw new Error('浏览器不支持流式响应')
    const reader = response.body.getReader(), decoder = new TextDecoder(), parser = new SSEDecoder()
    let terminal = false
    try {
      while (true) {
        const { value, done } = await reader.read()
        for (const event of parser.feed(decoder.decode(value, { stream: !done }), done)) {
          terminal ||= ['done', 'error'].includes(event.type)
          yield event
        }
        if (done) break
      }
      if (!terminal) throw new Error('连接中断，正在恢复已保存的记录')
    } finally { await reader.cancel().catch(() => {}); reader.releaseLock() }
  }
}

export const api = new ApiClient()
