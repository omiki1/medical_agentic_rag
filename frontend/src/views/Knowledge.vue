<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api/ApiClient.js'
import Icon from '../components/AppIcon.vue'
const emit = defineEmits(['source', 'ask', 'error'])
defineProps({ status: Object })
const query = ref(''), reviewed = ref(true), rows = ref([]), total = ref(0), offset = ref(0), busy = ref(false), graph = ref(null)
const showOriginal = ref(new Set())
function toggleOriginal(id, hasZh) { if (!hasZh) return; const next = new Set(showOriginal.value); next.has(id) ? next.delete(id) : next.add(id); showOriginal.value = next }
async function search(reset = true) {
  if (reset) offset.value = 0
  busy.value = true
  try { const data = await api.get(`/api/knowledge?q=${encodeURIComponent(query.value)}&reviewed=${reviewed.value}&offset=${offset.value}`); rows.value = data.items; total.value = data.total }
  catch (e) { emit('error', e.message) } finally { busy.value = false }
}
async function showGraph(entity) { try { graph.value = await api.get(`/api/graph?entity=${encodeURIComponent(entity)}`) } catch (e) { emit('error', e.message) } }
const relationNames = { DISEASE_SYMPTOM: '症状', DISEASE_DRUG: '相关药物', DISEASE_CHECK: '检查', DISEASE_DEPARTMENT: '科室', DISEASE_CUREWAY: '治疗方式', DISEASE_ACOMPANY: '并发症', DISEASE_DO_EAT: '饮食记录', DISEASE_NOT_EAT: '不宜饮食记录' }
onMounted(search)
</script>
<template><section class="page-content"><div class="page-title"><span class="eyebrow">KNOWLEDGE EXPLORER</span><h1>知识与来源</h1><p>从疾病条目走向原始证据，查看同源图谱中的每一条关系。</p></div>
  <div v-if="status" class="metric-grid"><article><span>来源已核验</span><strong>{{ status.corpus.source_checked_documents.toLocaleString() }}</strong><small>WHO、NHS、NIDDK 等公开资料</small></article><article><span>历史疾病文档</span><strong>{{ (status.corpus.documents - status.corpus.source_checked_documents).toLocaleString() }}</strong><small>探索模式可检索</small></article><article><span>全部知识文档</span><strong>{{ status.corpus.documents.toLocaleString() }}</strong><small>QA 数据集已停用</small></article><article><span>回答方式</span><strong style="font-size:23px">{{ status.generation === 'grounded_synthesis' ? '证据式解释' : '离线摘录' }}</strong><small>逐项引用与主题检查</small></article></div>
  <form class="search-bar" @submit.prevent="search()"><Icon name="search" /><input v-model="query" aria-label="搜索知识库" placeholder="搜索疾病名称，例如：高血压、肺结核" maxlength="120"><button class="primary" :disabled="busy">{{ busy ? '检索中…' : '检索' }}</button></form>
  <div class="list-toolbar"><span>找到 <b>{{ total.toLocaleString() }}</b> 个条目</span><label class="check-label"><input type="checkbox" v-model="reviewed" @change="search()">只看来源已核验的资料</label></div>
  <p v-if="!reviewed" class="notice">原始医学语料的来源、时效和内容尚待专业复核。这里展示原始记录，不将其作为个体用药依据。</p>
  <div class="knowledge-grid"><article v-for="doc in rows" :key="doc.id" class="knowledge-card"><div class="source-top"><span class="tag">{{ doc.source_type === 'public_health' ? '公共卫生机构资料' : doc.source_type === 'qa' ? '历史问答（已停用）' : '历史疾病条目' }}</span><span class="muted">{{ doc.published_at || '日期未知' }}</span></div><h2>{{ doc.title_zh || doc.title }}</h2><p>{{ showOriginal.has(doc.id) ? doc.text : (doc.text_zh || doc.text) }}</p><div class="card-actions"><button @click="emit('source', { document: doc, methods: [] })">查看来源 <Icon name="right" :size="13" /></button><button v-if="doc.entity" @click="showGraph(doc.entity)">关系图谱 <Icon name="graph" :size="14" /></button><button v-if="doc.text_zh" class="lang-toggle" @click="toggleOriginal(doc.id, true)">{{ showOriginal.has(doc.id) ? '显示译文' : '显示原文' }}</button></div></article></div>
  <div v-if="!busy && !rows.length" class="empty-page"><Icon name="search" :size="32" /><h3>未找到匹配条目</h3><p>试试疾病全称，或取消来源筛选。</p></div>
  <div class="pagination"><button class="secondary" :disabled="!offset || busy" @click="offset -= 20; search(false)">上一页</button><span>{{ Math.floor(offset / 20) + 1 }} / {{ Math.max(1, Math.ceil(total / 20)) }}</span><button class="secondary" :disabled="offset + 20 >= total || busy" @click="offset += 20; search(false)">下一页</button></div>
  <div v-if="graph" class="graph-section"><div class="section-heading"><div><span class="eyebrow">PROVENANCE GRAPH</span><h2>{{ graph.entity }} · 关系溯源</h2></div><button class="icon-button" aria-label="关闭图谱" @click="graph = null"><Icon name="close" /></button></div><p class="notice">{{ graph.note }}</p><div class="graph-paths"><div v-for="(edge, i) in graph.edges.slice(0, 30)" :key="i" class="graph-path"><span>{{ edge.subject }}</span><i>{{ relationNames[edge.relation] || edge.relation }} →</i><span>{{ edge.object }}</span></div></div><p class="muted">本地同源路径 {{ graph.edges.length }} 条 · Neo4j 本次返回 {{ graph.neo4j_edges.length }} 条{{ graph.degraded ? ' · 连接已降级' : '' }}</p></div>
</section></template>
