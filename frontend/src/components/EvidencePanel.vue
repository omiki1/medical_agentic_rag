<script setup>
import { ref, computed } from 'vue'
import Icon from './AppIcon.vue'
import { sourceTitle } from '../api/Presentation.js'
const props = defineProps({ result: Object, trace: { type: Array, default: () => [] }, status: Object, busy: Boolean })
const emit = defineEmits(['source', 'close'])
const tab = ref('sources')
const events = computed(() => props.result?.trace || props.trace)
const sources = computed(() => props.result?.evidence || [])
const methods = { entity_lookup: '实体检索', bm25: 'BM25', dense: '向量', qa_bm25: 'QA 全文', qa_dense: 'QA 向量', graph: '图谱', hyde: 'HyDE', neo4j_verified: 'Neo4j 核验', pubmed: 'PubMed' }
const showOriginal = ref(new Set())
function toggleOriginal(id, hasZh) { if (!hasZh) return; const next = new Set(showOriginal.value); next.has(id) ? next.delete(id) : next.add(id); showOriginal.value = next }
</script>
<template>
  <aside id="evidence-inspector" class="evidence-panel" aria-label="证据观察台" @keydown.esc="emit('close')">
    <div class="panel-heading"><button class="panel-close icon-button" aria-label="收起证据观察台" @click="emit('close')"><Icon name="close" /></button><span class="eyebrow">EVIDENCE INSPECTOR</span><h2>证据观察台 <span class="live-dot" :class="{ pulse: busy }"></span></h2><p>看见来源，也看见回答的边界。</p></div>
    <div class="segmented"><button :class="{ active: tab === 'sources' }" @click="tab = 'sources'">参考来源 <span>{{ sources.length }}</span></button><button :class="{ active: tab === 'trace' }" @click="tab = 'trace'">执行过程 <span>{{ events.length }}</span></button></div>
    <div class="panel-body">
      <template v-if="tab === 'sources'">
        <div v-if="!sources.length" class="inspector-empty"><div class="empty-line-icon"><Icon name="doc" :size="30" /></div><h3>{{ busy ? '正在寻找相关证据' : '从一个问题开始' }}</h3><p>{{ busy ? '来源完成检索后会出现在这里。' : '回答的来源、发布日期和检索路径，将在这里逐条呈现。' }}</p><div class="source-preview"><i></i><i></i><i></i></div></div>
        <button v-for="ev in sources" :key="ev.document.id" class="source-card" @click="emit('source', ev)">
          <div class="source-top"><span class="citation-label">{{ ev.citation_id || '文献' }}</span><span class="source-grade" :class="{ unreviewed: ev.document.review_status !== 'source_checked' }">{{ ev.document.review_status === 'source_checked' ? '来源已核验' : '内容待复核' }}</span></div>
          <h3>{{ ev.document.title_zh || ev.document.title }}</h3><p>{{ showOriginal.has(ev.document.id) ? ev.document.text : (ev.document.text_zh || ev.document.text) }}</p><div class="source-meta">{{ sourceTitle(ev.document) }}<span>{{ ev.document.published_at || '日期未知' }}</span></div>
          <div class="method-tags"><span v-for="m in ev.methods" :key="m">{{ methods[m] || m }}</span><span v-if="ev.document.text_zh" class="lang-toggle" @click.stop="toggleOriginal(ev.document.id, true)">{{ showOriginal.has(ev.document.id) ? '显示译文' : '显示原文' }}</span></div>
        </button>
        <div v-if="result?.evidence_grade?.missing.length" class="gap-note"><Icon name="warning" /><div><strong>还缺少这些信息</strong><p v-for="gap in result.evidence_grade.missing" :key="gap">{{ gap }}</p></div></div>
      </template>
      <template v-else>
        <div v-if="!events.length" class="inspector-empty"><Icon name="graph" :size="32" /><h3>每一步都有记录</h3><p>这里展示实际执行的检索与校验步骤。</p></div>
        <div v-for="event in events" :key="event.sequence" class="trace-step" :class="event.status"><span class="trace-number">{{ String(event.sequence).padStart(2, '0') }}</span><div><strong>{{ event.label }}</strong><small>{{ event.elapsed_ms }} ms <span v-if="event.iteration">· 第 {{ event.iteration }} 轮</span></small><details v-if="Object.keys(event.detail).length"><summary>查看执行详情</summary><pre>{{ JSON.stringify(event.detail, null, 2) }}</pre></details></div></div>
      </template>
    </div>
    <div class="panel-footer"><Icon name="lock" /><span>引用可验证，不等于临床结论已验证。</span></div>
  </aside>
</template>
