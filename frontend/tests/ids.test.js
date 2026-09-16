import test from 'node:test'
import assert from 'node:assert/strict'
import { uuid } from '../src/api/Ids.js'

const V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/

test('uuid returns an RFC 4122 version 4 identifier', () => {
  for (let i = 0; i < 200; i += 1) assert.match(uuid(), V4)
})

test('uuid stays unique across many calls', () => {
  const seen = new Set()
  for (let i = 0; i < 5000; i += 1) seen.add(uuid())
  assert.equal(seen.size, 5000)
})

test('uuid works when crypto has no randomUUID (plain HTTP is not a secure context)', () => {
  // 线上真实故障：http://公网IP 下 crypto.randomUUID 不存在，crypto 只有 getRandomValues。
  const insecure = {
    getRandomValues(array) {
      for (let i = 0; i < array.length; i += 1) array[i] = (i * 37 + 11) % 256
      return array
    },
  }
  assert.equal(typeof insecure.randomUUID, 'undefined')
  for (let i = 0; i < 50; i += 1) assert.match(uuid(insecure), V4)
})

test('uuid fallback still varies between calls without crypto', () => {
  const values = new Set()
  for (let i = 0; i < 500; i += 1) values.add(uuid(undefined))
  assert.ok(values.size > 400, `期望基本不重复，实际去重后 ${values.size}`)
})

test('uuid sets the version and variant bits correctly in fallback mode', () => {
  const insecure = { getRandomValues: (a) => { a.fill(0xff); return a } }
  const value = uuid(insecure)
  assert.match(value, V4)
  assert.equal(value[14], '4')            // version nibble
  assert.ok(['8', '9', 'a', 'b'].includes(value[19])) // variant
})
