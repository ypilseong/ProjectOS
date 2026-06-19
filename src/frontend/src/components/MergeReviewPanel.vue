<template>
  <div class="merge-review-panel">
    <el-empty
      v-if="candidates.length === 0"
      description="검토할 병합 후보가 없습니다"
    />
    <div v-else class="candidate-list">
      <el-card
        v-for="c in candidates"
        :key="c.keep_id + '|' + c.candidate_id"
        class="candidate-card"
        shadow="hover"
      >
        <div class="card-head">
          <el-tag size="small" type="info">{{ c.type }}</el-tag>
          <span class="confidence">{{ Math.round((c.confidence ?? 0) * 100) }}%</span>
        </div>
        <div class="merge-line">
          <strong>{{ c.keep_name }}</strong>
          <span class="arrow">←</span>
          <span class="dup">{{ c.candidate_name }}</span>
        </div>
        <div v-if="c.aliases && c.aliases.length" class="aliases">
          <el-tag
            v-for="alias in c.aliases"
            :key="alias"
            size="small"
            effect="plain"
            class="alias-chip"
          >
            {{ alias }}
          </el-tag>
        </div>
        <div class="card-actions">
          <el-button
            type="primary"
            size="small"
            :loading="isBusy(c)"
            @click="approve(c)"
          >
            승인
          </el-button>
          <el-button
            size="small"
            :loading="isBusy(c)"
            @click="reject(c)"
          >
            거부
          </el-button>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { projectsApi } from '../api/client.js'
import { extractMergeCandidates } from '../lib/mergeCandidates.js'

const props = defineProps({
  projectId: { type: String, required: true },
  graphData: { type: Object, default: null },
})
const emit = defineEmits(['merged'])

const candidates = ref(extractMergeCandidates(props.graphData))
const busyKey = ref(null)

watch(
  () => props.graphData,
  (gd) => {
    candidates.value = extractMergeCandidates(gd)
  },
)

function keyOf(c) {
  return c.keep_id + '|' + c.candidate_id
}

function isBusy(c) {
  return busyKey.value === keyOf(c)
}

async function approve(c) {
  busyKey.value = keyOf(c)
  try {
    const r = await projectsApi.applyMergeCandidate(props.projectId, {
      keep_id: c.keep_id,
      candidate_id: c.candidate_id,
    })
    candidates.value = r.data.merge_candidates ?? []
    ElMessage.success(`병합 적용: ${c.keep_name} ← ${c.candidate_name}`)
    emit('merged')
  } catch (e) {
    if (e?.response?.status === 409) {
      ElMessage.warning('이미 변경된 후보입니다. 그래프를 다시 불러옵니다.')
      emit('merged')
    } else {
      ElMessage.error('병합 적용에 실패했습니다.')
    }
  } finally {
    busyKey.value = null
  }
}

async function reject(c) {
  busyKey.value = keyOf(c)
  try {
    const r = await projectsApi.rejectMergeCandidate(props.projectId, {
      keep_id: c.keep_id,
      candidate_id: c.candidate_id,
    })
    candidates.value = r.data.merge_candidates ?? []
    ElMessage.info(`거부됨: ${c.keep_name} ← ${c.candidate_name}`)
  } catch (e) {
    ElMessage.error('거부 처리에 실패했습니다.')
  } finally {
    busyKey.value = null
  }
}
</script>

<style scoped>
.merge-review-panel {
  height: 500px;
  overflow-y: auto;
  padding: 8px;
}
.candidate-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.confidence {
  font-weight: 600;
  color: #409eff;
}
.merge-line {
  font-size: 15px;
  margin-bottom: 8px;
}
.merge-line .arrow {
  margin: 0 8px;
  color: #909399;
}
.merge-line .dup {
  color: #909399;
}
.aliases {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 10px;
}
.card-actions {
  display: flex;
  gap: 8px;
}
</style>
