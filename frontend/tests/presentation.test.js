import test from 'node:test'
import assert from 'node:assert/strict'
import { sourceTitle, sourceUrl } from '../src/api/Presentation.js'
test('internal provenance is hidden while original publishers remain', () => {
  for (const value of ['原始 medical.json（待复核）', 'C:\\private\\data.jsonl', 'file:///records.csv']) assert.equal(sourceTitle({source_title:value}), '医学知识资料')
  assert.equal(sourceTitle({source_title:'世界卫生组织 WHO'}), '世界卫生组织 WHO')
  assert.equal(sourceUrl({source_url:'javascript:alert(1)'}), '')
  assert.equal(sourceUrl({source_url:'file:///records.json'}), '')
  assert.equal(sourceUrl({source_url:'https://www.who.int/news'}), 'https://www.who.int/news')
})
