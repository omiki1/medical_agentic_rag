import test from 'node:test'
import assert from 'node:assert/strict'
import { SSEDecoder, api } from '../src/api/ApiClient.js'

test('SSE frames survive every chunk boundary, CRLF and heartbeat comments', () => {
  const wire = ': heartbeat\r\n\r\ndata: {"type":"result","data":{"answer":"甲亢 [E1]"}}\r\n\r\ndata: {"type":"done"}\r\n\r\n'
  for (let cut = 0; cut <= wire.length; cut++) {
    const parser = new SSEDecoder()
    const events = [...parser.feed(wire.slice(0, cut)), ...parser.feed(wire.slice(cut), true)]
    assert.equal(events[0].data.answer, '甲亢 [E1]')
    assert.equal(events[1].type, 'done')
    assert.equal(events.length, 2)
  }
})

test('truncated and oversized frames fail explicitly', () => {
  assert.throws(() => new SSEDecoder().feed('data: {"type":"result"}', true), /中断/)
  assert.throws(() => new SSEDecoder().feed('x'.repeat(2_000_001)), /过大/)
})

test('streaming client preserves split UTF-8 and detects a missing terminal event', async () => {
  const originalFetch = globalThis.fetch
  const response = (text) => new Response(new ReadableStream({
    start(controller) {
      for (const byte of new TextEncoder().encode(text)) controller.enqueue(new Uint8Array([byte]))
      controller.close()
    }
  }), { headers: { 'Content-Type': 'text/event-stream' } })
  try {
    globalThis.fetch = async () => response('data: {"type":"result","data":{"answer":"你好，甲亢"}}\n\ndata: {"type":"done"}\n\n')
    const events = []
    for await (const event of api.chat({ question: '合成测试' })) events.push(event)
    assert.equal(events[0].data.answer, '你好，甲亢')
    globalThis.fetch = async () => response('data: {"type":"result"}\n\n')
    await assert.rejects(async () => { for await (const event of api.chat({})) void event }, /连接中断/)
  } finally { globalThis.fetch = originalFetch }
})
