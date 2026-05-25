<template>
  <div class="chat-panel">
    <div class="chat-header">
      <el-icon><ChatDotRound /></el-icon>
      <span>그래프 채팅 (InsightForge)</span>
    </div>

    <div class="messages" ref="messagesEl">
      <div
        v-for="(msg, i) in messages"
        :key="i"
        :class="['msg', msg.role]"
      >
        <div class="msg-bubble">
          <pre class="msg-text">{{ msg.content }}</pre>
        </div>
      </div>
      <div v-if="streaming" class="msg assistant">
        <div class="msg-bubble">
          <pre class="msg-text">{{ streamBuffer }}<span class="cursor">▌</span></pre>
        </div>
      </div>
    </div>

    <div class="chat-input">
      <el-input
        v-model="input"
        type="textarea"
        :rows="2"
        placeholder="그래프에 대해 질문하세요... (예: 내 ML 프로젝트는 몇 개인가요?)"
        @keydown.ctrl.enter.prevent="send"
        :disabled="streaming"
        resize="none"
      />
      <div class="input-actions">
        <span class="hint">Ctrl+Enter로 전송</span>
        <el-button
          type="primary"
          :loading="streaming"
          @click="send"
          :disabled="!input.trim()"
        >전송</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue'
import { chatStreamUrl } from '../api/client.js'

const props = defineProps({
  projectId: { type: String, required: true },
})

const messages = ref([])
const input = ref('')
const streaming = ref(false)
const streamBuffer = ref('')
const messagesEl = ref(null)

async function send() {
  const question = input.value.trim()
  if (!question || streaming.value) return

  messages.value.push({ role: 'user', content: question })
  input.value = ''
  streaming.value = true
  streamBuffer.value = ''
  await scrollBottom()

  try {
    const resp = await fetch(chatStreamUrl(props.projectId), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    })

    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`)
    }

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''
      for (const line of lines) {
        if (!line.startsWith('data:')) continue
        try {
          const data = JSON.parse(line.slice(5).trim())
          if (data.token) {
            streamBuffer.value += data.token
            await scrollBottom()
          } else if (data.done) {
            messages.value.push({ role: 'assistant', content: streamBuffer.value })
            streamBuffer.value = ''
          }
        } catch {
          // ignore malformed lines
        }
      }
    }
  } catch (e) {
    messages.value.push({
      role: 'assistant',
      content: `오류: ${e.message}`,
    })
  } finally {
    streaming.value = false
    if (streamBuffer.value) {
      messages.value.push({ role: 'assistant', content: streamBuffer.value })
      streamBuffer.value = ''
    }
    await scrollBottom()
  }
}

async function scrollBottom() {
  await nextTick()
  if (messagesEl.value) {
    messagesEl.value.scrollTop = messagesEl.value.scrollHeight
  }
}
</script>

<style scoped>
.chat-panel { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
.chat-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: bold;
  padding: 12px 16px;
  border-bottom: 1px solid #eee;
  background: white;
  flex-shrink: 0;
}
.messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: #f8f9fa;
}
.msg { display: flex; }
.msg.user { justify-content: flex-end; }
.msg.assistant { justify-content: flex-start; }
.msg-bubble {
  max-width: 80%;
  border-radius: 12px;
  padding: 10px 14px;
}
.msg.user .msg-bubble { background: #409eff; color: white; }
.msg.assistant .msg-bubble { background: white; border: 1px solid #e4e7ed; }
.msg-text {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  font-size: 14px;
  line-height: 1.5;
  margin: 0;
}
.cursor { animation: blink 1s infinite; }
@keyframes blink { 50% { opacity: 0; } }
.chat-input {
  padding: 12px 16px;
  border-top: 1px solid #eee;
  background: white;
  flex-shrink: 0;
}
.input-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 6px;
}
.hint { font-size: 12px; color: #999; }
</style>
