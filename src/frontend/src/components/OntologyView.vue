<template>
  <div class="ontology-view">
    <div class="section-title">엔티티 타입 ({{ ontology.entity_types?.length || 0 }}종)</div>
    <div class="entity-grid">
      <el-card
        v-for="et in ontology.entity_types"
        :key="et.name"
        class="entity-card"
        shadow="hover"
      >
        <template #header>
          <el-tag :color="getTypeColor(et.name)" effect="dark">{{ et.name }}</el-tag>
        </template>
        <p class="desc">{{ et.description }}</p>
        <div v-if="et.examples?.length" class="examples">
          <el-tag
            v-for="ex in et.examples.slice(0, 3)"
            :key="ex"
            size="small"
            type="info"
            class="example-tag"
          >{{ ex }}</el-tag>
        </div>
      </el-card>
    </div>

    <el-divider />

    <div class="section-title">관계 타입 ({{ ontology.edge_types?.length || 0 }}종)</div>
    <el-table :data="ontology.edge_types" stripe border size="small">
      <el-table-column prop="name" label="관계 타입" width="180">
        <template #default="{ row }">
          <el-tag type="warning" effect="plain">{{ row.name }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="설명" />
      <el-table-column label="소스 → 대상" width="220">
        <template #default="{ row }">
          <span class="type-flow">
            {{ row.source_types?.join(', ') || '-' }}
            <el-icon><ArrowRight /></el-icon>
            {{ row.target_types?.join(', ') || '-' }}
          </span>
        </template>
      </el-table-column>
    </el-table>

    <div v-if="ontology.analysis_summary" class="analysis-summary">
      <el-divider />
      <div class="section-title">분석 요약</div>
      <el-text class="summary-text">{{ ontology.analysis_summary }}</el-text>
    </div>
  </div>
</template>

<script setup>
import { ArrowRight } from '@element-plus/icons-vue'

defineProps({
  ontology: {
    type: Object,
    default: () => ({ entity_types: [], edge_types: [], analysis_summary: '' }),
  },
})

const TYPE_COLORS = {
  Person: '#4A90D9',
  Project: '#5BA85B',
  Skill: '#E8A838',
  Organization: '#9B59B6',
  Publication: '#E74C3C',
  Role: '#E67E22',
  Achievement: '#27AE60',
  Event: '#2980B9',
  Institution: '#8E44AD',
}

function getTypeColor(name) {
  return TYPE_COLORS[name] || '#95A5A6'
}
</script>

<style scoped>
.ontology-view { padding: 8px 0; }
.section-title { font-weight: bold; font-size: 15px; margin-bottom: 12px; color: #303133; }
.entity-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.entity-card { min-height: 80px; }
.desc { font-size: 13px; color: #666; margin: 4px 0; line-height: 1.5; }
.examples { display: flex; gap: 4px; flex-wrap: wrap; margin-top: 8px; }
.example-tag { max-width: 100px; overflow: hidden; text-overflow: ellipsis; }
.type-flow { display: flex; align-items: center; gap: 4px; font-size: 13px; }
.analysis-summary { margin-top: 8px; }
.summary-text { line-height: 1.7; color: #444; white-space: pre-wrap; }
</style>
