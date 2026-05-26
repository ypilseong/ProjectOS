<template>
  <div class="stats-panel">
    <div class="stat-row">
      <el-statistic title="전체 노드" :value="stats.total_nodes" />
      <el-statistic title="전체 엣지" :value="stats.total_edges" />
    </div>

    <template v-if="hasNodeTypes">
      <el-divider content-position="left"><span class="divider-label">노드 타입별</span></el-divider>
      <div v-for="(count, type) in stats.nodes_by_type" :key="type" class="type-row">
        <el-tag :color="getColor(type)" effect="dark" size="small" class="type-tag">{{ type }}</el-tag>
        <el-progress
          :percentage="nodePercent(count)"
          :stroke-width="10"
          :color="getColor(type)"
          :show-text="false"
          style="flex: 1"
        />
        <span class="count">{{ count }}</span>
      </div>
    </template>

    <template v-if="hasEdgeTypes">
      <el-divider content-position="left"><span class="divider-label">관계 타입별</span></el-divider>
      <div v-for="(count, rel) in stats.edges_by_type" :key="rel" class="type-row">
        <span class="rel-name">{{ rel }}</span>
        <span class="count">{{ count }}</span>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  stats: {
    type: Object,
    default: () => ({
      total_nodes: 0,
      total_edges: 0,
      nodes_by_type: {},
      edges_by_type: {},
    }),
  },
})

const TYPE_COLORS = {
  Person: '#4A90D9',
  Project: '#5BA85B',
  Skill: '#E8A838',
  Organization: '#9B59B6',
  Publication: '#E74C3C',
  Technology: '#1ABC9C',
  Role: '#E67E22',
  Achievement: '#27AE60',
  Event: '#2980B9',
  Institution: '#8E44AD',
}

const hasNodeTypes = computed(() =>
  Object.keys(props.stats.nodes_by_type || {}).length > 0
)
const hasEdgeTypes = computed(() =>
  Object.keys(props.stats.edges_by_type || {}).length > 0
)

function getColor(type) {
  return TYPE_COLORS[type] || '#95A5A6'
}

function nodePercent(count) {
  const values = Object.values(props.stats.nodes_by_type || {})
  const max = Math.max(...values, 1)
  return Math.round((count / max) * 100)
}
</script>

<style scoped>
.stats-panel { display: flex; flex-direction: column; gap: 4px; }
.stat-row { display: flex; gap: 24px; justify-content: center; padding: 12px 0; }
.type-row { display: flex; align-items: center; gap: 8px; margin: 3px 0; }
.type-tag { min-width: 80px; text-align: center; }
.count { font-weight: bold; min-width: 28px; text-align: right; font-size: 13px; }
.rel-name { flex: 1; font-size: 12px; color: #666; }
.divider-label { font-size: 11px; color: #999; }
</style>
