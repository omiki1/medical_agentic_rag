<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { api } from '../api/ApiClient.js'
import { uuid } from '../api/Ids.js'
import { sourceTitle, sourceUrl } from '../api/Presentation.js'
import ModelSettings from './ModelSettings.vue'
import Settings from './Settings.vue'
const emit = defineEmits(['logout'])
const props = defineProps({ account: Object })
import Icon from '../components/AppIcon.vue'
import EvidencePanel from '../components/EvidencePanel.vue'
import Knowledge from './Knowledge.vue'
import Memory from './Memory.vue'
import Evaluation from './Evaluation.vue'

const adminNav = [{ id: 'chat', title: '知识问答', icon: 'chat' }, { id: 'knowledge', title: '知识与来源', icon: 'book' }, { id: 'memory', title: '四层记忆', icon: 'memory' }, { id: 'evaluation', title: '评测与质量', icon: 'chart' }, { id: 'settings', title: '系统设置', icon: 'memory' }]
const isAdmin = computed(() => session.value?.user?.role_name === 'admin')
const nav = computed(() => isAdmin.value ? adminNav : adminNav.filter(x => x.id === 'chat'))
const modelSettings = ref(null)
const page = ref('chat'), status = ref(null), session = ref(null), conversations = ref([]), activeId = ref(null)
const mode = ref('authoritative')
const runs = ref([]), selected = ref(null), question = ref(''), search = ref(''), busy = ref(false), initializing = ref(true), error = ref('')
const messageArea = ref(null), composer = ref(null), dialog = ref(null), modal = ref(null), mobileMenu = ref(false)
const authMode = ref('login'), authEmail = ref(''), authPassword = ref(''), authName = ref(''), authBusy = ref(false), authError = ref('')
const sourceOriginal = ref(false)
const sourceLoading = ref(false)
const evidenceOpen = ref(false), evidenceToggle = ref(null)
async function showEvidence(id) { if (!isAdmin.value) return; if (id) selected.value = id; evidenceOpen.value = true; await nextTick(); document.querySelector('#evidence-inspector .panel-close')?.focus() }
async function closeEvidence() { evidenceOpen.value = false; await nextTick(); evidenceToggle.value?.focus() }
function displayAnswer(text) { return text.replace(/^探索模式[:：][^\n]*\n\s*/, '') }
let controller, noticeTimer
const visibleConversations = computed(() => conversations.value.filter(x => x.title.toLowerCase().includes(search.value.toLowerCase())))
const activeTitle = computed(() => conversations.value.find(x => x.id === activeId.value)?.title || '新对话')
const selectedRun = computed(() => runs.value.find(r => r.id === selected.value) || runs.value.at(-1))
const currentResult = computed(() => selectedRun.value?.result || null)
const outcome = { answered: '有来源支持', abstained: '证据不足', emergency: '需要紧急就医', clarification: '请补充信息', out_of_scope: '超出范围' }
const prompts = [
  { icon: 'doc', title: '从症状认识疾病', text: '高血压有哪些症状？' },
  { icon: 'graph', title: '探索药物关联', text: '糖尿病和二甲双胍有什么关系？' },
  { icon: 'check', title: '理解预防与管理', text: '哮喘如何减少诱因？' },
  { icon: 'book', title: '对比基础医学知识', text: '高血压和糖尿病如何预防？' },
]
function notify(text) { error.value = text; clearTimeout(noticeTimer); noticeTimer = setTimeout(() => error.value = '', 8000) }
async function refreshHistory() { conversations.value = await api.get('/api/conversations') }
async function initialize() {
  initializing.value = true
  try { session.value = await api.session(); if (session.value.mode !== 'account') { emit('logout'); return }; [status.value, conversations.value, modelSettings.value] = await Promise.all([isAdmin.value ? api.get('/api/status') : api.get('/api/health'), api.get('/api/conversations'), api.get('/api/model-settings')]) }
  catch (e) { notify(e.message) } finally { initializing.value = false }
}
async function scrollBottom() { await nextTick(); if (messageArea.value) messageArea.value.scrollTop = messageArea.value.scrollHeight }
async function newChat() {
  // 任何入口点击都必须有可见结果：先落到对话页（正在生成的回答就在这里，可直接看进度），
  // 再说明为什么此刻不能开新对话。绝不再静默 return —— 静默会让用户以为界面坏了。
  page.value = 'chat'; mobileMenu.value = false
  if (busy.value) { await scrollBottom(); notify('上一条回答仍在生成中，完成后才能开启新对话。可先点「停止」中断。'); return }
  activeId.value = null; runs.value = []; selected.value = null; await nextTick(); composer.value?.focus()
}
async function openConversation(id) {
  page.value = 'chat'; mobileMenu.value = false
  if (busy.value) { await scrollBottom(); notify('上一条回答仍在生成中，完成后再切换对话。可先点「停止」中断。'); return }
  try { const data = await api.get(`/api/conversations/${id}`); activeId.value = id; runs.value = data.runs; selected.value = runs.value.at(-1)?.id; mode.value = runs.value.at(-1)?.mode || 'authoritative'; scrollBottom() }
  catch (e) { notify(e.message) }
}
async function send(text = question.value) {
  text = text.trim()
  // 先切页再校验：从任何入口发起提问，都应立刻看到对话页，而不是停在原页面。
  page.value = 'chat'; mobileMenu.value = false
  if (!text) return
  if (initializing.value) { notify('正在连接工作空间，请稍候再发送。'); return }
  if (busy.value) { await scrollBottom(); notify('上一条回答仍在生成中，请稍候。可先点「停止」中断后再提问。'); return }
  if (!modelSettings.value?.configured) { page.value = 'model'; notify('请先填写自己的模型 API，再开始对话。'); return }
  busy.value = true; question.value = ''; error.value = ''
  controller = new AbortController()
  let savedRunId = null, run = null
  // 注意：item 的构造必须留在 try 内部。它以前在 try 之前，
  // 一旦构造抛异常（线上就发生过：非安全上下文下 crypto.randomUUID 不存在），
  // finally 不会执行，busy 会永久卡在 true，整个界面只剩一个无效的「停止」按钮。
  try {
    const item = { id: uuid(), mode: mode.value, question: text, result: null, trace: [], status: 'running', created: Date.now() / 1000 }
    if (!activeId.value) { const conv = await api.post('/api/conversations'); activeId.value = conv.id }
    runs.value.push(item); selected.value = item.id; await scrollBottom()
    run = runs.value.at(-1)
    for await (const event of api.chat({ conversation_id: activeId.value, request_id: uuid(), question: text, mode: item.mode }, controller.signal)) {
      if (event.type === 'start') { savedRunId = event.run_id; run.id = savedRunId; selected.value = savedRunId }
      if (event.type === 'trace') run.trace.push(event.data)
      if (event.type === 'result') { run.result = event.data; run.status = 'completed'; await scrollBottom() }
      if (event.type === 'error') throw new Error(event.message)
    }
  } catch (e) {
    if (run && !run.result) {
      run.status = e.name === 'AbortError' ? 'cancelled' : 'failed'
      // 把真实原因留在这一条问答上，别让用户只看到"未完成"却不知道发生了什么。
      if (e.name !== 'AbortError') run.error = e.message
      if (savedRunId) {
        try { const saved = await api.get(`/api/runs/${savedRunId}`); if (saved.result) Object.assign(run, saved) } catch { /* Keep the visible failure state. */ }
      }
      if (e.name !== 'AbortError' && !run.result) notify(e.message)
    } else if (!run) notify(e.message)
  } finally { busy.value = false; controller = null; try { await refreshHistory() } catch (e) { notify(e.message) }; await nextTick(); composer.value?.focus() }
}
function keydown(event) { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); send() } }
async function openModal(data) { modal.value = data; sourceOriginal.value = false; authError.value = ''; await nextTick(); dialog.value.showModal() }
function closeModal() { dialog.value?.close(); modal.value = null; authPassword.value = '' }
function source(ev) { openModal({ kind: 'source', evidence: ev }) }
async function translateSource() {
  const current = modal.value
  if (current?.kind !== 'source' || sourceLoading.value) return
  sourceLoading.value = true
  try {
    const doc = await api.get(`/api/knowledge/${encodeURIComponent(current.evidence.document.id)}`)
    if (modal.value === current) {
      if (doc.text_zh) { current.evidence = { ...current.evidence, document: doc }; sourceOriginal.value = false }
      else notify('中文译文暂未完成，可继续查看原文。')
    }
  } catch (e) { notify(e.message) } finally { sourceLoading.value = false }
}
function cite(id, result) { const ev = result.evidence.find(e => e.citation_id === id); if (ev) source(ev) }
function segments(text) { return text.split(/(\[E\d+\])/g).filter(Boolean).map(value => ({ value, citation: /^\[E\d+\]$/.test(value) ? value.slice(1, -1) : null })) }
async function confirmDelete() {
  try { await api.delete(`/api/conversations/${modal.value.id}`); if (activeId.value === modal.value.id) await newChat(); closeModal(); await refreshHistory() } catch (e) { notify(e.message); closeModal() }
}
function exportConversation() {
  const text = `# ${activeTitle.value}\n\n` + runs.value.map(r => `## 问：${r.question}\n\n模式：${r.mode === 'exploratory' ? '探索' : '权威'}\n\n${r.result ? displayAnswer(r.result.answer) : '回答未完成'}\n\n` + (r.result?.evidence || []).map(e => `[${e.citation_id || e.document.id}] ${sourceTitle(e.document)} · ${sourceUrl(e.document) || '医学知识资料'} · ${e.document.published_at || '日期未知'}`).join('\n')).join('\n\n---\n\n')
  const url = URL.createObjectURL(new Blob([text], { type: 'text/markdown;charset=utf-8' })), link = document.createElement('a')
  link.href = url; link.download = '医学证据问答.md'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
}
async function submitAuth() {
  authBusy.value = true; authError.value = ''
  try {
    if (authMode.value === 'register') { await api.post('/users/register', { username: authName.value, email: authEmail.value, password: authPassword.value }); authMode.value = 'login' }
    await api.post('/auth/login', { email: authEmail.value, password: authPassword.value })
    closeModal(); await newChat(); await initialize()
  } catch (e) { authError.value = e.message } finally { authBusy.value = false }
}
async function logout() { try { await api.post('/auth/logout'); evidenceOpen.value = false; status.value = null; session.value = null; await newChat(); emit('logout') } catch (e) { notify(e.message) } }
onMounted(initialize)
onBeforeUnmount(() => { controller?.abort(); clearTimeout(noticeTimer) })
</script>

<template><div class="workbench">
  <aside class="sidebar" :class="{ expanded: mobileMenu }">
    <a class="brand" href="#" @click.prevent="newChat"><img src="/favicon.svg" alt="" width="38" height="38"><div><strong>MediAtlas<span>医学</span></strong><small>EVIDENCE WORKSPACE</small></div></a>
    <button class="new-chat" @click="newChat"><Icon name="plus" />开启新对话<span>↗</span></button>
    <nav aria-label="工作台导航"><button v-for="item in nav" :key="item.id" :class="{ active: page === item.id }" @click="page = item.id; mobileMenu = false"><Icon :name="item.icon" /><span>{{ item.title }}</span><span v-if="item.id === 'memory'" class="nav-count">4</span></button></nav>
    <div class="history-label">最近对话 <span>{{ conversations.length }}</span></div>
    <label class="history-search"><Icon name="search" :size="14" /><input v-model="search" placeholder="搜索对话" aria-label="搜索对话历史"></label>
    <div class="history-list"><div v-for="conv in visibleConversations" :key="conv.id" class="history-item" :class="{ active: activeId === conv.id }"><button @click="openConversation(conv.id)"><Icon name="chat" :size="15" /><span>{{ conv.title }}</span></button><button class="history-delete" :disabled="busy" aria-label="删除对话" @click="openModal({ kind: 'delete', id: conv.id, title: conv.title })"><Icon name="delete" :size="13" /></button></div><p v-if="!visibleConversations.length" class="history-placeholder">{{ search ? '没有匹配的对话' : '你的探索，将留在这里。' }}</p></div>
    <div class="sidebar-bottom"><button class="secondary model-settings-entry" @click="page = 'model'; mobileMenu = false"><Icon name="memory" :size="16" />模型设置<span>{{ modelSettings?.configured ? '已配置' : '待配置' }}</span></button><div class="environment"><span class="live-dot" :class="{ offline: !status }"></span>{{ status ? '工作空间已就绪' : '正在连接工作空间' }}<small>v1.0</small></div><div class="account-row"><span class="account-avatar"><Icon name="user" /></span><div><strong>{{ session?.user?.username || '本地访客' }}</strong><small>{{ isAdmin ? '管理员' : '个人账户' }}</small></div><button v-if="session?.mode === 'account'" class="icon-button" aria-label="退出登录" :disabled="busy" @click="logout"><Icon name="logout" /></button><button v-else class="text-button" :disabled="busy" @click="openModal({ kind: 'auth' })">登录</button></div></div>
  </aside>
  <div class="workspace-main"><header class="topbar"><div class="breadcrumb"><button class="mobile-toggle icon-button" aria-label="打开导航" @click="mobileMenu = !mobileMenu"><Icon name="book" /></button><span>工作空间</span><span class="slash">/</span><strong>{{ page === 'model' ? '模型设置' : nav.find(x => x.id === page)?.title }}</strong></div><div class="topbar-status"><span v-if="isAdmin" class="service-badge"><span class="live-dot" :class="{ offline: status?.neo4j !== 'connected' }"></span>Neo4j</span><span v-if="isAdmin" class="service-badge"><span class="live-dot" :class="{ offline: status?.redis !== 'connected' }"></span>Redis</span><span class="edition">{{ isAdmin ? '管理工作台' : '医学知识问答' }}</span></div></header>
    <div v-if="error" class="error-banner" role="alert"><Icon name="warning" /><span>{{ error }}</span><button class="text-button" v-if="!status" @click="initialize">重连</button><button class="icon-button" @click="error = ''" aria-label="关闭提示"><Icon name="close" :size="16" /></button></div>
    <div v-if="page === 'chat'" class="chat-layout" :class="{ 'evidence-open': evidenceOpen }"><main class="conversation-area"><header class="conversation-heading"><div><span class="tiny-square"></span><strong>{{ activeTitle }}</strong></div><div class="conversation-actions"><button v-if="isAdmin" ref="evidenceToggle" class="evidence-toggle secondary" :aria-expanded="evidenceOpen" aria-controls="evidence-inspector" @click="evidenceOpen ? closeEvidence() : showEvidence()"><Icon name="doc" :size="15" />{{ evidenceOpen ? '收起证据' : '证据与过程' }}</button><button class="icon-button" :disabled="!runs.length || busy" @click="exportConversation" aria-label="导出对话" title="导出对话"><Icon name="download" /></button></div></header>
      <div class="message-area" ref="messageArea">
        <section v-if="!runs.length" class="welcome"><span class="welcome-kicker"><i></i> 循证探索，从这里开始</span><h1>让每一个医学回答，<br><em>都有据可循。</em></h1><p class="welcome-description">连接医学文献与知识图谱，找回可核验的来源。<br>证据不足时，我们会明确告诉你。</p><div class="prompt-grid"><button v-for="prompt in prompts" :key="prompt.text" :disabled="initializing" @click="question = prompt.text; composer?.focus()"><div><span class="prompt-icon"><Icon :name="prompt.icon" /></span><Icon name="right" :size="15" /></div><strong>{{ prompt.title }}</strong><p>{{ prompt.text }}</p></button></div><div class="capability-strip"><span><Icon name="graph" :size="15" />多路检索</span><span><Icon name="doc" :size="15" />逐条溯源</span><span v-if="isAdmin"><Icon name="memory" :size="15" />四层记忆</span><span v-else><Icon name="chat" :size="15" />连续对话</span></div></section>
        <article v-for="run in runs" :key="run.id" class="exchange" :class="{ selected: selected === run.id }" @click="selected = run.id"><div class="user-message"><span class="message-label">你</span><p>{{ run.question }}</p></div><div class="assistant-message"><div class="answer-heading"><img src="/favicon.svg" alt="" width="25" height="25"><strong>MediAtlas</strong><span class="run-mode">{{ (run.mode || run.result?.mode) === 'exploratory' ? '探索' : '权威' }}</span><span v-if="run.result" class="answer-status" :class="run.result.status">{{ run.result.generation_mode === 'generation_unavailable' ? '解释未完成' : outcome[run.result.status] }}</span></div><div v-if="run.result" class="answer-content"><template v-for="(segment, i) in segments(displayAnswer(run.result.answer))" :key="i"><button v-if="segment.citation" class="inline-citation" @click.stop="cite(segment.citation, run.result)">{{ segment.citation }}</button><span v-else>{{ segment.value }}</span></template><div class="answer-footer"><span><Icon name="time" :size="13" />{{ (run.result.duration_ms / 1000).toFixed(1) }} 秒</span><span v-if="isAdmin">{{ run.result.iterations }} 轮检索</span><span v-if="isAdmin">{{ run.result.status !== 'answered' ? '范围与质量提示' : run.result.generation_mode === 'grounded_synthesis' ? '基于证据解释' : '来源摘录' }}</span><button v-if="isAdmin" @click.stop="showEvidence(run.id)">查看证据与过程 <Icon name="right" :size="12" /></button></div></div><div v-else-if="run.status === 'running'" class="running-state" role="status"><span class="loading-ring"></span><span>{{ isAdmin ? (run.trace?.at(-1)?.label || '正在读取上下文…') : '正在整理回答…' }}</span></div><div v-else class="interrupted"><Icon name="warning" /><span>{{ run.status === 'cancelled' ? '回答已停止。' : (run.error || '这次回答未完成。') }}</span><button class="text-button" :disabled="busy" @click.stop="send(run.question)">重新提问</button></div></div></article>
      </div>
      <footer class="composer-area"><div class="mode-controls"><div class="mode-switch" role="group" aria-label="回答模式"><button type="button" :disabled="busy" :aria-pressed="mode === 'authoritative'" :class="{ active: mode === 'authoritative' }" @click="mode = 'authoritative'">权威模式</button><button type="button" :disabled="busy" :aria-pressed="mode === 'exploratory'" :class="{ active: mode === 'exploratory' }" @click="mode = 'exploratory'">探索模式</button></div><small>{{ mode === 'authoritative' ? '核验来源 · 严格覆盖' : '公开来源 + 历史疾病资料' }}</small></div><form class="composer" @submit.prevent="send()"><textarea ref="composer" v-model="question" rows="2" maxlength="2000" aria-label="输入医学问题" placeholder="输入医学问题，或继续追问…" @keydown="keydown"></textarea><div class="composer-bottom"><span><span class="live-dot" :class="{ offline: !status }"></span>{{ isAdmin ? (status?.dense ? '混合检索已就绪' : '关键词检索') : (modelSettings?.configured ? '已连接个人模型配置' : '请先配置模型') }}<small>· Enter 发送，Shift + Enter 换行</small></span><button v-if="busy" type="button" class="stop-button" @click="controller?.abort()"><span></span>停止</button><button v-else class="send-button" :disabled="!question.trim() || initializing" aria-label="发送问题"><Icon name="send" :size="21" /></button></div></form><p class="composer-note">用于医学知识探索，不替代诊断或处方。紧急情况请联系当地急救服务。</p></footer>
    </main><EvidencePanel v-if="isAdmin && evidenceOpen" @close="closeEvidence" :result="currentResult" :trace="selectedRun?.trace || []" :status="status" :busy="busy" @source="source" /></div>
    <Knowledge v-else-if="isAdmin && page === 'knowledge'" :status="status" @source="source" @ask="send" @error="notify" />
    <Memory v-else-if="isAdmin && page === 'memory'" @error="notify" @conversation="openConversation" />
    <Evaluation v-else-if="isAdmin && page === 'evaluation'" @error="notify" />
    <Settings v-else-if="isAdmin && page === 'settings'" :status="status" />
    <ModelSettings v-else-if="page === 'model'" @saved="modelSettings = $event" @error="notify" />
  </div>
  <dialog ref="dialog" @cancel.prevent="closeModal" class="app-dialog"><button class="dialog-close icon-button" aria-label="关闭窗口" @click="closeModal"><Icon name="close" /></button>
    <template v-if="modal?.kind === 'source'"><span class="eyebrow">SOURCE DETAIL</span><h2>{{ modal.evidence.document.title_zh || modal.evidence.document.title }}</h2><div class="source-detail-meta"><span class="tag">{{ modal.evidence.document.review_status === 'source_checked' ? '已核对公开来源，未经过临床审定' : '原始语料，待专业复核' }}</span><p>来源：{{ sourceTitle(modal.evidence.document) }}</p><p v-if="modal.evidence.document.published_at">发布：{{ modal.evidence.document.published_at }}</p></div><blockquote>{{ sourceOriginal ? modal.evidence.document.text : (modal.evidence.document.text_zh || modal.evidence.document.text) }}</blockquote><button v-if="modal.evidence.document.text_zh" class="text-button lang-toggle-inline" @click="sourceOriginal = !sourceOriginal">{{ sourceOriginal ? '显示中文译文' : '显示英文原文' }}</button><div v-if="isAdmin && modal.evidence.graph_paths?.length" class="graph-paths"><div v-for="(path, i) in modal.evidence.graph_paths" :key="i" class="graph-path"><span>{{ path[0] }}</span><i>{{ path[1] }} →</i><span>{{ path[2] }}</span></div></div><a v-if="sourceUrl(modal.evidence.document)" class="primary external-link" :href="sourceUrl(modal.evidence.document)" target="_blank" rel="noopener noreferrer">访问原始来源 ↗</a></template>
    <template v-else-if="modal?.kind === 'delete'"><span class="eyebrow">DELETE CONVERSATION</span><h2>删除这段对话？</h2><p>“{{ modal.title }}”的问答、执行记录和短期缓存将被删除。</p><div class="dialog-actions"><button class="secondary" @click="closeModal">取消</button><button class="danger-button" @click="confirmDelete">删除对话</button></div></template>
    <form v-else-if="modal?.kind === 'auth'" class="auth-form" @submit.prevent="submitAuth"><span class="eyebrow">YOUR PRIVATE WORKSPACE</span><h2>{{ authMode === 'login' ? '登录你的工作空间' : '创建账户' }}</h2><p>延续探索记录和你确认的长期记忆。</p><label v-if="authMode === 'register'">用户名<input v-model="authName" required minlength="2" maxlength="40" autocomplete="nickname"></label><label>邮箱<input v-model="authEmail" type="email" required autocomplete="username"></label><label>密码<input v-model="authPassword" type="password" required :minlength="authMode === 'register' ? 10 : 1" maxlength="128" :autocomplete="authMode === 'register' ? 'new-password' : 'current-password'" placeholder="注册密码至少 10 位"></label><p v-if="authError" class="form-error" role="alert">{{ authError }}</p><button class="primary" :disabled="authBusy">{{ authBusy ? '处理中…' : authMode === 'login' ? '登录' : '注册并登录' }}</button><button type="button" class="text-button" @click="authMode = authMode === 'login' ? 'register' : 'login'; authError = ''">{{ authMode === 'login' ? '还没有账户？创建账户' : '已有账户？返回登录' }}</button></form>

  </dialog>
</div></template>
