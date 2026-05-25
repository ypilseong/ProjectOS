<template>
  <div class="graph-view">
    <div class="graph-toolbar">
      <el-checkbox-group v-model="visibleTypes" size="small" @change="redraw">
        <el-checkbox-button
          v-for="t in allTypes"
          :key="t"
          :value="t"
          :style="{ '--el-checkbox-button-checked-bg-color': getColor(t) }"
        >{{ t }}</el-checkbox-button>
      </el-checkbox-group>
      <el-button size="small" @click="resetZoom" class="reset-btn">Reset</el-button>
    </div>
    <svg ref="svgEl" class="graph-svg" />
    <el-drawer
      v-model="drawerVisible"
      direction="rtl"
      size="340px"
      :title="selectedNode?.name || ''"
    >
      <div v-if="selectedNode" class="node-detail">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="타입">
            <el-tag :color="getColor(selectedNode.type)" effect="dark">{{ selectedNode.type }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="설명">
            {{ selectedNode.description || '-' }}
          </el-descriptions-item>
          <el-descriptions-item v-if="selectedNode.source_files?.length" label="소스">
            {{ selectedNode.source_files.join(', ') }}
          </el-descriptions-item>
        </el-descriptions>
        <div v-if="connectedNodes.length" class="connected-section">
          <div class="section-label">연결 노드 ({{ connectedNodes.length }}개)</div>
          <div class="connected-tags">
            <el-tag
              v-for="n in connectedNodes"
              :key="n.id"
              :color="getColor(n.type)"
              effect="dark"
              size="small"
              class="conn-tag"
            >{{ n.name }}</el-tag>
          </div>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import * as d3 from 'd3'

const props = defineProps({
  graphData: { type: Object, default: null },
})

const svgEl = ref(null)
const drawerVisible = ref(false)
const selectedNode = ref(null)
const connectedNodes = ref([])
const visibleTypes = ref([])
let simulation = null

const NODE_COLORS = {
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
  default: '#95A5A6',
}

function getColor(type) {
  return NODE_COLORS[type] || NODE_COLORS.default
}

const allTypes = computed(() => {
  if (!props.graphData?.nodes) return []
  return [...new Set(props.graphData.nodes.map(n => n.type || 'Unknown'))]
})

watch(
  () => props.graphData,
  (data) => {
    if (data) {
      visibleTypes.value = [...allTypes.value]
      draw(data)
    }
  },
  { immediate: true }
)

watch(visibleTypes, () => {
  if (props.graphData) draw(props.graphData)
})

function draw(data) {
  if (!svgEl.value || !data) return
  if (simulation) simulation.stop()

  const svg = d3.select(svgEl.value)
  svg.selectAll('*').remove()

  const width = svgEl.value.clientWidth || 800
  const height = svgEl.value.clientHeight || 600

  const filteredNodes = data.nodes.filter(n =>
    visibleTypes.value.includes(n.type || 'Unknown')
  )
  const filteredIdSet = new Set(filteredNodes.map(n => n.id))
  const links = (data.links || []).filter(l => {
    const srcId = typeof l.source === 'object' ? l.source.id : l.source
    const tgtId = typeof l.target === 'object' ? l.target.id : l.target
    return filteredIdSet.has(srcId) && filteredIdSet.has(tgtId)
  })

  // Clone nodes/links for D3 to mutate
  const nodes = filteredNodes.map(n => ({ ...n }))
  const linksClone = links.map(l => ({
    ...l,
    source: typeof l.source === 'object' ? l.source.id : l.source,
    target: typeof l.target === 'object' ? l.target.id : l.target,
  }))

  svg.attr('viewBox', `0 0 ${width} ${height}`)

  const g = svg.append('g')

  const zoom = d3.zoom()
    .scaleExtent([0.1, 6])
    .on('zoom', (e) => g.attr('transform', e.transform))
  svg.call(zoom)

  // Store refs for resetZoom
  svgEl.value.__d3zoom = zoom
  svgEl.value.__d3svg = svg

  // Arrow marker
  svg.append('defs').append('marker')
    .attr('id', 'arrow')
    .attr('viewBox', '0 -5 10 10')
    .attr('refX', 20)
    .attr('markerWidth', 6)
    .attr('markerHeight', 6)
    .attr('orient', 'auto')
    .append('path')
    .attr('d', 'M0,-5L10,0L0,5')
    .attr('fill', '#ccc')

  const link = g.append('g').selectAll('line')
    .data(linksClone)
    .enter().append('line')
    .attr('stroke', '#ddd')
    .attr('stroke-width', 1.5)
    .attr('marker-end', 'url(#arrow)')

  const linkLabel = g.append('g').selectAll('text')
    .data(linksClone)
    .enter().append('text')
    .attr('font-size', 8)
    .attr('fill', '#aaa')
    .attr('text-anchor', 'middle')
    .text(d => d.relation || '')

  const node = g.append('g').selectAll('g')
    .data(nodes)
    .enter().append('g')
    .style('cursor', 'pointer')
    .on('click', (_, d) => onNodeClick(d, data))
    .call(
      d3.drag()
        .on('start', (e, d) => {
          if (!e.active) simulation.alphaTarget(0.3).restart()
          d.fx = d.x
          d.fy = d.y
        })
        .on('drag', (e, d) => {
          d.fx = e.x
          d.fy = e.y
        })
        .on('end', (e, d) => {
          if (!e.active) simulation.alphaTarget(0)
          d.fx = null
          d.fy = null
        })
    )

  node.append('circle')
    .attr('r', d => d.type === 'Person' ? 14 : 10)
    .attr('fill', d => getColor(d.type))
    .attr('stroke', '#fff')
    .attr('stroke-width', 2)

  node.append('text')
    .attr('dy', '0.35em')
    .attr('text-anchor', 'middle')
    .attr('font-size', 9)
    .attr('fill', '#fff')
    .attr('pointer-events', 'none')
    .text(d => (d.name || d.id || '').slice(0, 8))

  simulation = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(linksClone).id(d => d.id).distance(80))
    .force('charge', d3.forceManyBody().strength(-200))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collision', d3.forceCollide(20))
    .on('tick', () => {
      link
        .attr('x1', d => d.source.x)
        .attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x)
        .attr('y2', d => d.target.y)
      linkLabel
        .attr('x', d => (d.source.x + d.target.x) / 2)
        .attr('y', d => (d.source.y + d.target.y) / 2)
      node.attr('transform', d => `translate(${d.x},${d.y})`)
    })
}

function onNodeClick(d, data) {
  selectedNode.value = d
  const allLinks = data.links || []
  const neighbors = allLinks
    .filter(l => {
      const srcId = typeof l.source === 'object' ? l.source.id : l.source
      const tgtId = typeof l.target === 'object' ? l.target.id : l.target
      return srcId === d.id || tgtId === d.id
    })
    .map(l => {
      const srcId = typeof l.source === 'object' ? l.source.id : l.source
      const tgtId = typeof l.target === 'object' ? l.target.id : l.target
      const otherId = srcId === d.id ? tgtId : srcId
      const other = data.nodes.find(n => n.id === otherId)
      return other ? { id: otherId, name: other.name, type: other.type } : null
    })
    .filter(Boolean)
  connectedNodes.value = neighbors
  drawerVisible.value = true
}

function resetZoom() {
  if (svgEl.value?.__d3svg && svgEl.value?.__d3zoom) {
    svgEl.value.__d3svg.call(svgEl.value.__d3zoom.transform, d3.zoomIdentity)
  }
}

function redraw() {
  if (props.graphData) draw(props.graphData)
}

onUnmounted(() => {
  if (simulation) simulation.stop()
})
</script>

<style scoped>
.graph-view { position: relative; height: 100%; display: flex; flex-direction: column; }
.graph-svg { flex: 1; width: 100%; background: #fafafa; border-radius: 8px; min-height: 400px; }
.graph-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 8px;
  background: white;
  border-bottom: 1px solid #eee;
}
.reset-btn { margin-left: auto; }
.node-detail { padding: 8px 0; }
.connected-section { margin-top: 16px; }
.section-label { font-size: 12px; color: #999; margin-bottom: 6px; }
.connected-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.conn-tag { margin: 2px; }
</style>
