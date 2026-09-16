<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api/ApiClient.js'
import Icon from '../components/AppIcon.vue'
const emit = defineEmits(['error', 'conversation'])
const state = ref(null), kind = ref('response_style'), value = ref('简洁'), confirmed = ref(false), editing = ref(null), busy = ref(false)
const labels = { response_style: '回答偏好', learning_focus: '学习关注', background: '确认的背景' }
async function load() { try { state.value = await api.get('/api/memory') } catch (e) { emit('error', e.message) } }
async function save() {
  busy.value = true
  try { const body = { kind: kind.value, value: value.value, confirmed: confirmed.value }; await (editing.value ? api.patch(`/api/memory/${editing.value}`, body) : api.post('/api/memory', body)); reset(); await load() }
  catch (e) { emit('error', e.message) } finally { busy.value = false }
}
function reset() { editing.value = null; confirmed.value = false; kind.value = 'response_style'; value.value = '简洁' }
function edit(item) { editing.value = item.id; kind.value = item.kind; value.value = item.value; confirmed.value = false }
async function remove(item) { try { await api.delete(`/api/memory/${item.id}`); await load() } catch (e) { emit('error', e.message) } }
onMounted(load)
</script>
<template><section class="page-content"><div class="page-title"><span class="eyebrow">MEMORY, WITH BOUNDARIES</span><h1>四层记忆</h1><p>记住上下文，保留出处。由你决定哪些信息值得长期记住。</p></div>
  <div class="memory-layers"><article v-for="layer in [{ n: '01', title: '工作记忆', sub: '当前请求', text: '问题、计划和证据在本次请求内使用，完成后释放。' }, { n: '02', title: '短期记忆', sub: `Redis · ${state?.redis === 'connected' ? '已连接' : '数据库降级'}`, text: `最近 ${state?.recent_turns || 6} 轮对话，缓存 ${Math.round((state?.short_term_ttl || 86400) / 3600)} 小时。` }, { n: '03', title: '情节记忆', sub: '持久化历史', text: '保留问答、来源和执行记录，可回顾和删除。' }, { n: '04', title: '长期语义记忆', sub: '需要明确确认', text: '你的偏好和背景，不会从提问自动推断诊断。' }]" :key="layer.n"><span class="layer-number">{{ layer.n }}</span><h2>{{ layer.title }}</h2><span class="tag">{{ layer.sub }}</span><p>{{ layer.text }}</p></article></div>
  <div class="memory-columns"><div><div class="section-heading"><h2>已确认的长期记忆</h2><span class="tag">{{ state?.semantic?.length || 0 }} / 50</span></div><div v-if="!state?.semantic?.length" class="empty-page compact"><Icon name="memory" :size="30" /><h3>这里由你来定义</h3><p>例如“我正在学习呼吸系统疾病”或“回答简洁”。</p></div><article v-for="item in state?.semantic || []" :key="item.id" class="memory-item"><div><span class="eyebrow">{{ labels[item.kind] }}</span><p>{{ item.value }}</p><small>由你确认 · {{ new Date(item.updated * 1000).toLocaleDateString('zh-CN') }}</small></div><div class="item-actions"><button class="icon-button" aria-label="修改记忆" @click="edit(item)"><Icon name="edit" /></button><button class="icon-button danger" aria-label="删除记忆" @click="remove(item)"><Icon name="delete" /></button></div></article></div>
    <form class="memory-form" @submit.prevent="save"><h2>{{ editing ? '修改记忆' : '添加一条记忆' }}</h2><label>记忆类型<select v-model="kind" @change="value = kind === 'response_style' ? '简洁' : ''"><option v-for="(label, key) in labels" :key="key" :value="key">{{ label }}</option></select></label><label>内容<select v-if="kind === 'response_style'" v-model="value"><option>简洁</option><option>详细</option></select><textarea v-else v-model="value" maxlength="500" rows="4" placeholder="输入你确认的信息…"></textarea></label><label class="check-label"><input type="checkbox" v-model="confirmed">我确认保存此信息，可随时修改或删除</label><button class="primary" :disabled="!confirmed || !value.trim() || busy">{{ busy ? '保存中…' : '保存记忆' }}</button><button v-if="editing" type="button" class="text-button" @click="reset">取消修改</button><p class="subtle">访客记忆保存在当前设备会话中。注册并登录后，可在该账户下持续使用。</p></form></div>
  <div class="episode-section"><div class="section-heading"><h2>最近的情节记忆</h2><span class="muted">仅展示你的已完成问答</span></div><button v-for="episode in state?.episodes || []" :key="episode.id" class="episode-row" @click="emit('conversation', episode.conversation_id)"><Icon name="chat" /><span>{{ episode.question }}</span><small>{{ new Date(episode.created * 1000).toLocaleString('zh-CN') }}</small><Icon name="right" /></button><p v-if="!state?.episodes?.length" class="muted">完成一次问答后，将在这里保留可回顾的记录。</p></div>
</section></template>
