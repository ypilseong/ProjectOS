<template>
  <el-drawer
    :model-value="visible"
    @update:model-value="$emit('update:visible', $event)"
    title="문서 분석 결과"
    direction="rtl"
    size="480px"
  >
    <div v-if="analysisData" class="analysis-content">
      <div class="summary-box">
        <p class="summary-text">{{ analysisData.summary }}</p>
        <div class="generated-at">분석일: {{ formatDate(analysisData.generated_at) }}</div>
      </div>

      <el-tabs v-model="innerTab" class="result-tabs">
        <el-tab-pane label="개선 포인트" name="issues">
          <div v-if="!analysisData.issues?.length" class="no-issues">
            <el-empty description="발견된 문제가 없습니다" :image-size="80" />
          </div>
          <div v-else class="issues-list">
            <el-card
              v-for="(issue, idx) in analysisData.issues"
              :key="idx"
              class="issue-card"
              :body-style="{ padding: '12px' }"
            >
              <div class="issue-header">
                <el-tag :color="severityColor(issue.severity)" effect="dark" size="small">
                  {{ severityLabel(issue.severity) }}
                </el-tag>
                <span class="issue-category">{{ issue.category }}</span>
              </div>
              <p class="issue-description">{{ issue.description }}</p>
              <div class="issue-suggestion">
                <el-icon><ArrowRight /></el-icon>
                <span>{{ issue.suggestion }}</span>
              </div>
            </el-card>
          </div>
        </el-tab-pane>

        <el-tab-pane label="개선 초안" name="draft">
          <el-scrollbar height="500px">
            <pre class="draft-text">{{ analysisData.improved_draft }}</pre>
          </el-scrollbar>
        </el-tab-pane>
      </el-tabs>
    </div>
  </el-drawer>
</template>

<script setup>
import { ref } from 'vue'
import { ArrowRight } from '@element-plus/icons-vue'

defineProps({
  visible: { type: Boolean, default: false },
  analysisData: { type: Object, default: null },
})

defineEmits(['update:visible'])

const innerTab = ref('issues')

function severityColor(severity) {
  return { high: '#E74C3C', medium: '#E8A838', low: '#95A5A6' }[severity] || '#95A5A6'
}

function severityLabel(severity) {
  return { high: '높음', medium: '중간', low: '낮음' }[severity] || severity
}

function formatDate(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleString('ko-KR', { dateStyle: 'short', timeStyle: 'short' })
}
</script>

<style scoped>
.analysis-content { display: flex; flex-direction: column; gap: 16px; }
.summary-box {
  background: #f0f9ff;
  border-left: 4px solid #409eff;
  padding: 12px 16px;
  border-radius: 4px;
}
.summary-text { margin: 0 0 6px; font-size: 14px; color: #303133; line-height: 1.6; }
.generated-at { font-size: 11px; color: #909399; }
.result-tabs { margin-top: 4px; }
.issues-list { display: flex; flex-direction: column; gap: 10px; padding: 4px 0; }
.issue-card { border-radius: 6px; }
.issue-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.issue-category { font-weight: bold; font-size: 14px; color: #303133; }
.issue-description { margin: 0 0 8px; font-size: 13px; color: #606266; }
.issue-suggestion {
  display: flex;
  align-items: flex-start;
  gap: 4px;
  font-size: 13px;
  color: #409eff;
  background: #ecf5ff;
  padding: 8px;
  border-radius: 4px;
}
.no-issues { padding: 32px 0; }
.draft-text {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.7;
  color: #303133;
  padding: 8px;
}
</style>
