<script setup>
import { ChatLineSquare, Collection, Connection, DataAnalysis, Plus, Search, Top, Close, ArrowRight, Document, Timer, CircleCheck, Warning, Delete, Download, Edit, Setting, Refresh, Lock, User, SwitchButton } from '@element-plus/icons-vue'
defineProps({ name: String, size: { default: 18 } })
const icons = { chat: ChatLineSquare, book: Collection, graph: Connection, chart: DataAnalysis, plus: Plus, search: Search, send: Top, close: Close, right: ArrowRight, doc: Document, time: Timer, check: CircleCheck, warning: Warning, delete: Delete, download: Download, edit: Edit, memory: Setting, refresh: Refresh, lock: Lock, user: User, logout: SwitchButton }
</script>
<template><span class="icon" :style="{ width: `${size}px`, height: `${size}px` }" aria-hidden="true"><component :is="icons[name] || Document" /></span></template>
