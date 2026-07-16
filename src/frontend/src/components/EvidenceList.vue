<template>
  <el-empty v-if="!items.length && empty" :description="empty" />
  <div v-else class="evidence-list">
    <div
      v-for="evidence in items"
      :key="evidence.id"
      :class="['evidence-card', { weak: evidence.isWeak, unresolved: !evidence.resolved }]"
    >
      <div class="evidence-head">
        <el-tag size="small" effect="plain">{{ evidence.id }}</el-tag>
        <el-tag
          v-if="evidence.directness"
          size="small"
          :type="evidence.directness === 'direct' ? 'success' : 'warning'"
        >
          {{ evidence.directness === 'direct' ? '직접' : '추론' }}
        </el-tag>
        <el-tag v-if="evidence.confidence !== null" size="small" :type="evidence.isWeak ? 'warning' : 'info'">
          {{ Math.round(evidence.confidence * 100) }}%
        </el-tag>
        <el-tag v-if="!evidence.resolved" size="small" type="danger">미해석</el-tag>
      </div>
      <strong class="evidence-title">{{ evidence.title }}</strong>
      <div v-if="evidence.source || evidence.page !== null" class="evidence-source">
        {{ evidence.source }}
        <span v-if="evidence.page !== null"> · p.{{ evidence.page }}</span>
      </div>
      <p v-if="evidence.quote" class="evidence-quote">
        “{{ evidence.quote }}”<span v-if="evidence.truncated"> …</span>
      </p>
      <div v-if="evidence.anchors && evidence.anchors.length > 1" class="evidence-anchors">
        <div v-for="(anchor, idx) in evidence.anchors" :key="idx" class="evidence-anchor">
          <el-tag size="small" :type="anchor.directness === 'direct' ? 'success' : 'warning'">
            {{ anchor.directness === 'direct' ? '직접' : '추론' }}
          </el-tag>
          <span>{{ anchor.source }}<template v-if="anchor.page !== null"> · p.{{ anchor.page }}</template></span>
          <small v-if="anchor.quote">“{{ anchor.quote }}”</small>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  items: { type: Array, default: () => [] },
  empty: { type: String, default: '' },
})
</script>

<style scoped>
.evidence-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.evidence-card {
  min-width: 0;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 10px 12px;
  background: white;
}
.evidence-card.weak { border-color: #faecd8; background: #fdf6ec; }
.evidence-card.unresolved { border-color: #fde2e2; background: #fef0f0; }
.evidence-head { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.evidence-title {
  display: block;
  margin-top: 6px;
  color: #303133;
  overflow-wrap: anywhere;
}
.evidence-source { color: #909399; font-size: 12px; margin-top: 2px; overflow-wrap: anywhere; }
.evidence-quote {
  margin: 8px 0 0;
  color: #606266;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
}
.evidence-anchors {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  border-top: 1px dashed #ebeef5;
  padding-top: 8px;
}
.evidence-anchor { display: flex; align-items: baseline; gap: 6px; flex-wrap: wrap; }
.evidence-anchor span { color: #909399; font-size: 12px; }
.evidence-anchor small { color: #606266; font-size: 12px; overflow-wrap: anywhere; }
</style>
