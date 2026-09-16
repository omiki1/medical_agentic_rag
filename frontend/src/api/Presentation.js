export function sourceTitle(doc = {}) {
  const title = doc.source_title || ''
  return /\.(?:jsonl?|sqlite|csv|parquet)\b|[a-z]:[\\/]|file:\/\//i.test(title) ? '医学知识资料' : (title || '医学知识资料')
}
export function sourceUrl(doc = {}) {
  try { const url = new URL(doc.source_url); return ['https:', 'http:'].includes(url.protocol) && !url.username ? url.href : '' } catch { return '' }
}
