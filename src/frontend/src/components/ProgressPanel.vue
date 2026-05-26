<template>
  <div class="progress-panel">
    <el-progress
      :percentage="progress"
      :status="progressStatus"
      :stroke-width="18"
    />
    <div class="progress-stats">
      <el-tag :type="statusTagType">{{ statusLabel }}</el-tag>
      <span class="message">{{ message }}</span>
    </div>
    <div class="log-area" ref="logEl">
      <div v-for="(log, i) in logs" :key="i" class="log-line">
        <span class="log-time">{{ log.time }}</span>
        <span :class="['log-msg', log.type]">{{ log.msg }}</span>
      </div>
    </div>
    <div v-if="error" class="mt-2">
      <el-alert :title="error" type="error" show-icon :closable="false" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onUnmounted, nextTick } from 'vue'
import { tasksApi } from '../api/client.js'

const props = defineProps({
  taskId: { type: String, default: null }
})
const emit = defineEmits(['completed', 'failed'])

const progress = ref(0)
const status = ref('pending')
const message = ref('')
const error = ref('')
const logs = ref([])
const logEl = ref(null)
let eventSource = null

const progressStatus = computed(() => {
  if (status.value === 'completed') return 'success'
  if (status.value === 'failed') return 'exception'
  return ''
})

const statusTagType = computed(() => {
  if (status.value === 'completed') return 'success'
  if (status.value === 'failed') return 'danger'
  if (status.value === 'running') return 'warning'
  return 'info'
})

const statusLabel = computed(() => ({
  pending: '대기 중',
  running: '실행 중',
  completed: '완료',
  failed: '실패',
})[status.value] || status.value)

watch(() => props.taskId, (id) => {
  if (id) startStream(id)
}, { immediate: true })

function startStream(taskId) {
  if (eventSource) eventSource.close()
  logs.value = []
  eventSource = new EventSource(tasksApi.streamUrl(taskId))
  eventSource.onmessage = async (e) => {
    const data = JSON.parse(e.data)
    progress.value = data.progress ?? 0
    status.value = data.status ?? 'pending'
    message.value = data.message ?? ''
    error.value = data.error ?? ''
    addLog(data.message, data.status === 'failed' ? 'error' : 'info')
    if (data.status === 'completed') {
      eventSource.close()
      emit('completed')
    } else if (data.status === 'failed') {
      eventSource.close()
      emit('failed', data.error)
    }
  }
  eventSource.onerror = () => {
    eventSource.close()
  }
}

function addLog(msg, type = 'info') {
  if (!msg) return
  logs.value.push({ time: new Date().toLocaleTimeString(), msg, type })
  nextTick(() => {
    if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight
  })
}

onUnmounted(() => {
  if (eventSource) eventSource.close()
})
</script>

<style scoped>
.progress-panel { display: flex; flex-direction: column; gap: 8px; }
.progress-stats {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 4px 0;
}
.message { font-size: 13px; color: #666; }
.log-area {
  height: 150px;
  overflow-y: auto;
  background: #1e1e1e;
  color: #ccc;
  padding: 8px;
  border-radius: 4px;
  font-family: 'Courier New', monospace;
  font-size: 12px;
}
.log-line { margin-bottom: 2px; }
.log-time { color: #888; margin-right: 8px; }
.log-msg.error { color: #f56c6c; }
.mt-2 { margin-top: 8px; }
</style>
