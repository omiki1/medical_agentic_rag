<script setup>
import { ref } from 'vue'
import { api } from '../api/ApiClient.js'
defineProps({ connectionError: String })
const emit = defineEmits(['authenticated'])
const register = ref(false), email = ref(''), password = ref(''), username = ref(''), busy = ref(false), error = ref('')
async function submit() {
  busy.value = true; error.value = ''
  try {
    await api.session()
    if (register.value) { await api.post('/users/register', { username: username.value, email: email.value, password: password.value }); register.value = false }
    await api.post('/auth/login', { email: email.value, password: password.value })
    password.value = ''; emit('authenticated')
  } catch (e) { error.value = e.message } finally { busy.value = false }
}
</script>
<template><main class="login-page">
  <section class="login-intro"><a class="brand" href="/"><img src="/favicon.svg" alt="" width="42" height="42"><div><strong>MediAtlas<span>医学</span></strong><small>MEDICAL KNOWLEDGE</small></div></a><div class="login-intro-copy"><span class="eyebrow">从理解身体开始</span><h1>把疑问说出来，<br>让健康知识<br><em>更容易理解。</em></h1><p>描述你的困惑，继续追问，<br>在清晰的回答中找到可查阅的资料。</p><div class="login-features"><span>连续对话</span><span>参考来源</span><span>个人模型</span></div></div><small>医学知识问答 · 不替代医生诊疗</small></section>
  <section class="login-form-panel"><form class="login-form auth-form" @submit.prevent="submit"><span class="eyebrow">WELCOME TO MEDIATLAS</span><h2>{{ register ? '创建你的账户' : '欢迎回来' }}</h2><p>{{ register ? '保存对话记录，使用自己的模型开始探索。' : '登录后，继续你的医学知识对话。' }}</p><label v-if="register">用户名<input v-model="username" required minlength="2" maxlength="40" autocomplete="nickname" placeholder="如何称呼你"></label><label>邮箱<input v-model="email" type="email" required autocomplete="username" maxlength="254" placeholder="you@example.com"></label><label>密码<input v-model="password" type="password" required :minlength="register ? 10 : 1" maxlength="128" :autocomplete="register ? 'new-password' : 'current-password'" :placeholder="register ? '至少 10 位' : '输入密码'"></label><p v-if="error || connectionError" class="form-error" role="alert">{{ error || connectionError }}</p><button class="primary" :disabled="busy">{{ busy ? '正在处理…' : register ? '注册并登录' : '登录' }}</button><button class="text-button" type="button" :disabled="busy" @click="register = !register; error = ''; password = ''">{{ register ? '已有账户？去登录' : '还没有账户？创建账户' }}</button><p class="login-privacy">对话仅在你的账户中可见。首次登录后，请在「模型设置」中填写自己的 API Key。</p></form><p class="login-footer">如遇紧急情况，请立即联系当地急救服务。</p></section>
</main></template>
