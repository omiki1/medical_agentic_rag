<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api/ApiClient.js'
const emit = defineEmits(['saved', 'error'])
const config = ref(null), providerId = ref(''), model = ref(''), key = ref(''), busy = ref(false), message = ref('')
const provider = computed(() => config.value?.providers.find(item => item.id === providerId.value))
const models = computed(() => provider.value?.models || [])
function chooseProvider() { model.value = models.value[0]?.id || ''; key.value = ''; message.value = '' }
async function load() {
  try {
    config.value = await api.get('/api/model-settings')
    providerId.value = config.value.provider_id || config.value.providers[0]?.id || ''
    const available = models.value.some(item => item.id === config.value.model)
    model.value = available ? config.value.model : (models.value[0]?.id || '')
  } catch (e) { emit('error', e.message) }
}
async function save() {
  busy.value = true; message.value = ''
  try { config.value = await api.post('/api/model-settings', { provider_id: providerId.value, model: model.value, api_key: key.value }); key.value = ''; message.value = '已保存。尚未验证接口可用性，可返回对话发送问题。'; emit('saved', config.value) }
  catch (e) { emit('error', e.message) } finally { busy.value = false }
}
async function remove() { busy.value = true; try { await api.delete('/api/model-settings'); key.value = ''; await load(); emit('saved', config.value); message.value = '已移除模型配置。' } catch (e) { emit('error', e.message) } finally { busy.value = false } }
onMounted(load)
</script>
<template><section class="page-content"><div class="page-title"><span class="eyebrow">YOUR MODEL</span><h1>模型设置</h1><p>选择模型服务商和模型，密钥仅用于你的账户。</p></div><form v-if="config" class="settings-form auth-form" @submit.prevent="save"><label>服务商<select v-model="providerId" required @change="chooseProvider"><option v-for="item in config.providers" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><label>模型<select v-model="model" required><option v-for="item in models" :key="item.id" :value="item.id">{{ item.name }}</option></select><small v-if="provider" class="muted">接口由系统自动配置：{{ provider.base_url }}</small></label><label>API Key<input v-model="key" type="password" :required="!config.configured || providerId !== config.provider_id" maxlength="4096" autocomplete="new-password" :placeholder="config.configured && providerId === config.provider_id ? '已加密保存；留空保留现有密钥' : '填写该服务商提供的 API Key'"></label><p class="notice">发送问题时，你的问题、相关对话上下文和检索资料会发送给所选模型服务商，用于生成和检查回答，可能产生 API 费用。请确认该服务商的数据处理规则，避免填写姓名、证件号码等无关信息。</p><div class="dialog-actions"><button class="primary" :disabled="busy || !models.length">{{ busy ? '处理中…' : '保存配置' }}</button><button v-if="config.configured" type="button" class="secondary" :disabled="busy" @click="remove">移除密钥</button></div><p v-if="message" role="status">{{ message }}</p><p class="muted">列表仅包含适配当前回答流程的文本模型。保存配置不会自动调用模型。</p></form><p v-else role="status">正在读取配置…</p></section></template>
