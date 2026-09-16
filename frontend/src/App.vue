<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { api } from './api/ApiClient.js'
import Chat from './views/Chat.vue'
import Login from './views/Login.vue'
const account = ref(null), loading = ref(true), error = ref('')
async function refresh() {
  loading.value = true; error.value = ''
  try { const s = await api.session(); account.value = s.mode === 'account' ? s : null }
  catch (e) { account.value = null; error.value = e.message }
  finally { loading.value = false }
}
function expired() { if (account.value) { account.value = null; refresh() } }
onMounted(() => { window.addEventListener('mediatlas:unauthorized', expired); refresh() })
onBeforeUnmount(() => window.removeEventListener('mediatlas:unauthorized', expired))
</script>
<template>
  <div v-if="loading" class="login-loading" role="status">正在连接 MediAtlas…</div>
  <Chat v-else-if="account" :account="account" @logout="refresh" />
  <Login v-else :connection-error="error" @authenticated="refresh" />
</template>
