<template>
  <div class="simulation-panel">
    <div class="simulation-header">
      <div>
        <h3>시뮬레이션</h3>
        <p>현재 프로젝트 그래프를 기준으로 persona simulation을 실행하고 변경 후보를 그래프 위에서 검토합니다.</p>
      </div>
      <el-button :loading="loadingResult" @click="loadSimulation">결과 불러오기</el-button>
    </div>

    <div class="simulation-controls">
      <el-input
        v-model="query"
        type="textarea"
        :rows="3"
        placeholder="검토 목표, CV 개선 방향, 그래프 보강 질문을 입력하세요"
      />
      <div class="control-row">
        <el-checkbox v-model="applyGraph">그래프에 변경 적용</el-checkbox>
        <el-checkbox v-model="updateVault">Vault 업데이트</el-checkbox>
        <el-button
          type="primary"
          :loading="running"
          :disabled="!graphData"
          @click="runSimulation"
        >
          시뮬레이션 실행
        </el-button>
      </div>
    </div>

    <ProgressPanel
      v-if="taskId"
      :task-id="taskId"
      class="simulation-progress"
      @completed="onSimulationCompleted"
      @failed="onSimulationFailed"
    />

    <el-empty v-if="!simulationResult && !taskId" description="아직 로드된 시뮬레이션 결과가 없습니다." />

    <template v-if="vm">
      <div class="summary-grid">
        <div class="summary-tile">
          <span>상태</span>
          <strong>{{ vm.status }}</strong>
        </div>
        <div class="summary-tile">
          <span>페르소나</span>
          <strong>{{ vm.personas.length }}</strong>
        </div>
        <div class="summary-tile">
          <span>그래프 변경</span>
          <strong>+{{ vm.graphChanges.nodes_added || 0 }} / +{{ vm.graphChanges.edges_added || 0 }}</strong>
        </div>
        <div class="summary-tile">
          <span>Delta 후보</span>
          <strong>{{ vm.graphDeltaItems.length }}</strong>
        </div>
      </div>

      <div class="workflow-strip">
        <button
          v-for="step in vm.workflowSteps"
          :key="step.id"
          type="button"
          :class="['workflow-step', statusClass(step.status)]"
        >
          <span class="step-status"></span>
          <strong>{{ step.label }}</strong>
          <small>{{ step.summary }}</small>
        </button>
      </div>

      <el-tabs v-model="activeTab" class="simulation-tabs">
        <el-tab-pane label="그래프" name="graph">
          <div class="graph-mode-row">
            <el-radio-group v-model="graphMode" size="small">
              <el-radio-button label="full">전체 그래프</el-radio-button>
              <el-radio-button label="used">사용된 그래프</el-radio-button>
              <el-radio-button label="highlight">수정 하이라이트</el-radio-button>
              <el-radio-button label="delta">Delta only</el-radio-button>
            </el-radio-group>
            <el-switch v-model="dimUnhighlighted" active-text="비관련 흐리게" />
          </div>
          <div class="simulation-graph">
            <GraphView
              :graph-data="displayGraphData"
              :highlight-node-ids="displayOverlay.highlightNodeIds"
              :highlight-link-ids="displayOverlay.highlightLinkIds"
              :dim-unhighlighted="graphMode === 'highlight' && dimUnhighlighted"
            />
          </div>
        </el-tab-pane>

        <el-tab-pane label="리포트" name="report">
          <div class="report-layout">
            <div class="section-list">
              <button
                v-for="section in vm.reportSections"
                :key="section.id"
                type="button"
                :class="{ active: selectedSectionId === section.id }"
                @click="selectedSectionId = section.id"
              >
                <strong>{{ section.title }}</strong>
                <small>{{ section.kind }}</small>
              </button>
            </div>
            <div v-if="selectedSection" class="section-detail">
              <div class="section-kind">{{ selectedSection.kind }}</div>
              <h4>{{ selectedSection.title }}</h4>
              <p v-if="selectedSection.summary">{{ selectedSection.summary }}</p>
              <pre v-if="selectedSection.body">{{ selectedSection.body }}</pre>
              <ul v-if="selectedSection.items.length">
                <li v-for="item in selectedSection.items" :key="item">{{ item }}</li>
              </ul>
              <div class="ref-row">
                <el-tag v-for="ref in selectedSection.evidenceRefs" :key="ref" size="small">{{ ref }}</el-tag>
              </div>
            </div>
          </div>
        </el-tab-pane>

        <el-tab-pane label="페르소나/토론" name="debate">
          <div class="persona-grid">
            <div v-for="persona in vm.personas" :key="persona.id" class="persona-item">
              <strong>{{ persona.name }}</strong>
              <span>{{ persona.role }}</span>
              <p v-if="persona.stance">{{ persona.stance }}</p>
              <ul>
                <li v-for="point in persona.focusAreas.concat(persona.keyPoints).slice(0, 5)" :key="point">{{ point }}</li>
              </ul>
            </div>
          </div>
          <div class="debate-list">
            <div v-for="round in vm.debateRounds" :key="round.round" class="debate-round">
              <div class="round-label">Round {{ round.round }}</div>
              <div v-for="turn in round.turns" :key="turn.id" class="turn-item">
                <strong>{{ turn.speakerName }}</strong>
                <p>{{ turn.claim }}</p>
                <span>{{ turn.proposal }}</span>
              </div>
            </div>
          </div>
        </el-tab-pane>

        <el-tab-pane label="Graph Delta" name="delta">
          <div class="delta-toolbar">
            <el-radio-group v-model="deltaStatus" size="small">
              <el-radio-button label="all">전체</el-radio-button>
              <el-radio-button label="proposed">Proposed</el-radio-button>
              <el-radio-button label="applied">Applied</el-radio-button>
              <el-radio-button label="skipped">Skipped</el-radio-button>
            </el-radio-group>
          </div>
          <div class="delta-list">
            <div v-for="delta in visibleDeltas" :key="delta.id" class="delta-item">
              <div class="delta-head">
                <el-tag size="small">{{ delta.operation }}</el-tag>
                <strong>{{ delta.label }}</strong>
                <el-tag size="small" :type="delta.status === 'applied' ? 'success' : 'warning'">{{ delta.status }}</el-tag>
              </div>
              <div class="delta-meta">
                {{ delta.type }} <span v-if="delta.relation">/ {{ delta.relation }}</span>
                <span v-if="delta.confidence !== null">/ confidence {{ Math.round(delta.confidence * 100) }}%</span>
              </div>
              <p v-if="delta.statusReason">{{ delta.statusReason }}</p>
              <div class="ref-row">
                <el-tag v-for="ref in delta.evidenceRefs" :key="ref" size="small" effect="plain">{{ ref }}</el-tag>
              </div>
            </div>
          </div>
        </el-tab-pane>

        <el-tab-pane label="Evidence" name="evidence">
          <div class="evidence-list">
            <div v-for="evidence in vm.evidenceRefs" :key="evidence.id" class="evidence-item">
              <el-tag size="small">{{ evidence.id }}</el-tag>
              <span>{{ evidence.source }}</span>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </template>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import GraphView from './GraphView.vue'
import ProgressPanel from './ProgressPanel.vue'
import { projectsApi } from '../api/client.js'
import { buildSimulationOverlay, buildSimulationViewModel } from '../lib/simulationViewModel.js'

const props = defineProps({
  projectId: { type: String, required: true },
  graphData: { type: Object, default: null },
})

const emit = defineEmits(['graph-updated'])

const query = ref('')
const taskId = ref(null)
const running = ref(false)
const loadingResult = ref(false)
const applyGraph = ref(true)
const updateVault = ref(true)
const simulationResult = ref(null)
const usedGraphData = ref(null)
const activeTab = ref('graph')
const graphMode = ref('highlight')
const dimUnhighlighted = ref(true)
const selectedSectionId = ref('')
const deltaStatus = ref('all')

const vm = computed(() => simulationResult.value ? buildSimulationViewModel(simulationResult.value) : null)

watch(vm, (value) => {
  selectedSectionId.value = value?.reportSections?.[0]?.id || ''
})

const selectedSection = computed(() =>
  vm.value?.reportSections.find(section => section.id === selectedSectionId.value)
)

const visibleDeltas = computed(() => {
  const deltas = vm.value?.graphDeltaItems || []
  return deltaStatus.value === 'all'
    ? deltas
    : deltas.filter(delta => delta.status === deltaStatus.value)
})

const displayOverlay = computed(() => {
  if (!simulationResult.value) return { graphData: props.graphData, highlightNodeIds: [], highlightLinkIds: [] }
  if (graphMode.value === 'used') {
    return { graphData: usedGraphData.value || props.graphData, highlightNodeIds: [], highlightLinkIds: [] }
  }
  if (graphMode.value === 'full') {
    return { graphData: props.graphData, highlightNodeIds: [], highlightLinkIds: [] }
  }
  return buildSimulationOverlay(props.graphData, simulationResult.value, graphMode.value)
})

const displayGraphData = computed(() => displayOverlay.value.graphData || props.graphData)

async function runSimulation() {
  running.value = true
  usedGraphData.value = cloneGraph(props.graphData)
  try {
    const response = await projectsApi.runSimulation(props.projectId, {
      query: query.value.trim(),
      apply_graph: applyGraph.value,
      update_vault: updateVault.value,
    })
    taskId.value = response.data.task_id
    activeTab.value = 'graph'
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '시뮬레이션을 시작할 수 없습니다.')
  } finally {
    running.value = false
  }
}

async function loadSimulation() {
  loadingResult.value = true
  try {
    const response = await projectsApi.getSimulation(props.projectId)
    simulationResult.value = response.data
    usedGraphData.value = graphFromSnapshot(simulationResult.value?.input_graph_snapshot) || usedGraphData.value
    if (simulationResult.value?.query) query.value = simulationResult.value.query
  } catch (error) {
    simulationResult.value = null
    ElMessage.warning(error?.response?.data?.detail || '저장된 시뮬레이션 결과가 없습니다.')
  } finally {
    loadingResult.value = false
  }
}

async function onSimulationCompleted() {
  taskId.value = null
  await loadSimulation()
  try {
    const graphResponse = await projectsApi.getGraph(props.projectId)
    emit('graph-updated', graphResponse.data)
  } catch {
    ElMessage.warning('시뮬레이션은 완료됐지만 최신 그래프를 다시 불러오지 못했습니다.')
  }
}

function onSimulationFailed(error) {
  taskId.value = null
  ElMessage.error(error || '시뮬레이션에 실패했습니다.')
}

function statusClass(status) {
  if (['completed', 'success', 'applied'].includes(status)) return 'success'
  if (['failed', 'rejected'].includes(status)) return 'failed'
  if (['running', 'partial', 'proposed'].includes(status)) return 'running'
  return 'waiting'
}

function cloneGraph(graph) {
  if (!graph) return null
  return JSON.parse(JSON.stringify(graph))
}

function graphFromSnapshot(snapshot) {
  if (!snapshot) return null
  return snapshot.graph || snapshot.data || snapshot
}
</script>

<style scoped>
.simulation-panel { display: flex; flex-direction: column; gap: 16px; }
.simulation-header,
.control-row,
.graph-mode-row,
.delta-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.simulation-header h3 { margin: 0 0 4px; color: #303133; }
.simulation-header p { margin: 0; color: #909399; font-size: 13px; }
.simulation-controls { display: flex; flex-direction: column; gap: 10px; }
.simulation-progress { border: 1px solid #ebeef5; border-radius: 8px; padding: 12px; }
.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(120px, 1fr));
  gap: 10px;
}
.summary-tile {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 12px;
  background: #fafcff;
}
.summary-tile span { display: block; color: #909399; font-size: 12px; margin-bottom: 4px; }
.summary-tile strong { color: #303133; font-size: 18px; }
.workflow-strip { display: flex; flex-wrap: wrap; gap: 8px; }
.workflow-step {
  width: 150px;
  min-height: 58px;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  background: white;
  text-align: left;
  padding: 8px;
  display: grid;
  grid-template-columns: 10px 1fr;
  gap: 2px 7px;
  color: #303133;
}
.workflow-step small {
  grid-column: 2;
  color: #909399;
  overflow-wrap: anywhere;
}
.step-status {
  grid-row: 1 / span 2;
  width: 8px;
  height: 8px;
  margin-top: 5px;
  border-radius: 50%;
  background: #c0c4cc;
}
.workflow-step.success .step-status { background: #67c23a; }
.workflow-step.running .step-status { background: #409eff; }
.workflow-step.failed .step-status { background: #f56c6c; }
.simulation-graph { height: 560px; border: 1px solid #ebeef5; border-radius: 8px; overflow: hidden; }
.report-layout {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 14px;
}
.section-list { display: flex; flex-direction: column; gap: 8px; }
.section-list button {
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  background: white;
  padding: 9px;
  text-align: left;
  cursor: pointer;
}
.section-list button.active { border-color: #409eff; background: #ecf5ff; }
.section-list small { display: block; color: #909399; margin-top: 3px; }
.section-detail {
  min-width: 0;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 14px;
}
.section-kind { color: #909399; font-size: 11px; text-transform: uppercase; }
.section-detail h4 { margin: 4px 0 8px; }
.section-detail p { color: #606266; line-height: 1.55; }
.section-detail pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  background: #f5f7fa;
  border-radius: 6px;
  padding: 10px;
  font-size: 13px;
}
.persona-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}
.persona-item,
.turn-item,
.delta-item,
.evidence-item {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 10px;
  background: white;
}
.persona-item span,
.turn-item span,
.delta-meta {
  color: #909399;
  font-size: 12px;
}
.persona-item p,
.turn-item p,
.delta-item p {
  color: #606266;
  font-size: 13px;
  overflow-wrap: anywhere;
}
.debate-list,
.delta-list,
.evidence-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.round-label { font-weight: 700; margin: 10px 0 6px; color: #303133; }
.delta-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.delta-head strong { overflow-wrap: anywhere; }
.ref-row { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 8px; }
.evidence-item { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
@media (max-width: 760px) {
  .summary-grid,
  .report-layout {
    grid-template-columns: 1fr;
  }
  .workflow-step { width: 100%; }
}
</style>
