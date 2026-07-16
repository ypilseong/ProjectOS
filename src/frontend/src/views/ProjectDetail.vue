<template>
  <div class="project-detail">
    <el-container v-if="simulationOnly" class="simulation-only-layout">
      <el-header class="simulation-only-header">
        <el-button text @click="router.push(`/projects/${projectId}`)">
          <el-icon><ArrowLeft /></el-icon> 프로젝트
        </el-button>
        <div>
          <strong>{{ project?.name || 'Simulation' }}</strong>
          <span>simulation visualization</span>
        </div>
      </el-header>
      <el-main class="simulation-only-main">
        <SimulationPanel
          :project-id="projectId"
          :graph-data="graphData"
          read-only
          @graph-updated="onSimulationGraphUpdated"
        />
      </el-main>
    </el-container>
    <el-container v-else style="height: 100vh">
      <!-- LEFT SIDEBAR -->
      <el-aside width="280px" class="sidebar">
        <div class="sidebar-header">
          <el-button text @click="router.push('/')">
            <el-icon><ArrowLeft /></el-icon> 홈
          </el-button>
          <div class="project-title">{{ project?.name || '로딩 중...' }}</div>
        </div>

        <el-divider />

        <div class="sidebar-section">
          <div class="sidebar-label">그래프 통계</div>
          <StatsPanel :stats="stats" />
        </div>

        <el-divider />
        <div class="sidebar-section">
          <div class="sidebar-label">커리어 프로필</div>
          <div v-if="profileTask">
            <ProgressPanel
              :task-id="profileTask"
              @completed="onProfileCompleted"
              @failed="onProfileFailed"
            />
          </div>
          <div v-else-if="profileData && profileData.length">
            <el-button size="small" type="success" plain style="width:100%;margin-bottom:6px"
                       @click="ElMessage.info('프로필 뷰어 준비 중')">
              프로필 보기 ({{ profileData.length }}개)
            </el-button>
            <el-button size="small" plain style="width:100%" :loading="profileRunning" @click="runProfiles">
              재생성
            </el-button>
          </div>
          <div v-else>
            <el-button
              size="small"
              type="primary"
              style="width:100%"
              :loading="profileRunning"
              :disabled="project?.status !== 'ready'"
              @click="runProfiles"
            >
              프로필 생성
            </el-button>
            <p style="font-size:11px;color:#909399;margin-top:6px">
              그래프 빌드 완료 후 실행 가능
            </p>
          </div>
        </div>

        <el-divider />
        <div class="sidebar-section">
          <div class="sidebar-label">Vault 파일</div>
          <VaultTree :project-id="projectId" :vault-tree="vaultTree" @add-files="goToUpload" />
        </div>

        <el-divider />
        <div class="sidebar-section">
          <div class="sidebar-label">문서 분석</div>
          <div v-if="analysisTask">
            <ProgressPanel
              :task-id="analysisTask"
              @completed="onAnalysisCompleted"
              @failed="onAnalysisFailed"
            />
          </div>
          <div v-else-if="analysisData">
            <el-button
              size="small"
              type="primary"
              plain
              style="width:100%;margin-bottom:6px"
              @click="analysisDrawerVisible = true"
            >
              분석 결과 보기
            </el-button>
            <el-button
              size="small"
              plain
              style="width:100%"
              :loading="analysisRunning"
              @click="runAnalysis"
            >
              재분석
            </el-button>
          </div>
          <div v-else>
            <el-button
              size="small"
              type="primary"
              style="width:100%"
              :loading="analysisRunning"
              @click="runAnalysis"
            >
              분석 실행
            </el-button>
            <p class="analysis-hint">파일 업로드 후 실행 가능</p>
          </div>
        </div>
      </el-aside>

      <!-- MAIN PANEL -->
      <el-main class="main-panel">
        <el-steps :active="activeStep" align-center class="steps" finish-status="success">
          <el-step title="파일 업로드" />
          <el-step title="온톨로지" />
          <el-step title="그래프 구축" />
          <el-step title="결과" />
          <el-step title="Vault" />
        </el-steps>

        <!-- Step 0: File Upload -->
        <div v-if="activeStep === 0" class="step-content">
          <h3 class="step-title">파일 업로드</h3>
          <p class="step-desc">이력서, 프로젝트 문서, 논문 등을 업로드하세요.</p>
          <FileUpload :project-id="projectId" @uploaded="onFilesUploaded" />
          <div v-if="currentTaskId" class="mt-3">
            <ProgressPanel
              :task-id="currentTaskId"
              @completed="onParseCompleted"
              @failed="onTaskFailed"
            />
          </div>
          <div v-if="!currentTaskId" class="step-nav">
            <el-button @click="activeStep = 1" type="primary" plain>
              온톨로지로 이동 →
            </el-button>
          </div>
        </div>

        <!-- Step 1: Ontology -->
        <div v-else-if="activeStep === 1" class="step-content">
          <h3 class="step-title">온톨로지 생성</h3>
          <p class="step-desc">문서 묶음을 확인한 뒤 목표에 맞춰 엔티티와 관계 타입을 정렬합니다.</p>
          <div v-if="!ontology" class="ontology-context">
            <el-skeleton v-if="ontologyContextLoading" :rows="4" animated />
            <template v-else>
              <div class="context-summary">
                <div>
                  <div class="context-label">파일 탐색 결과</div>
                  <strong>{{ ontologyOverview.summary || '파싱된 파일이 없습니다.' }}</strong>
                </div>
                <el-button size="small" plain @click="loadOntologyContext">새로고침</el-button>
              </div>
              <div v-if="ontologyOverview.files?.length" class="context-files">
                <div
                  v-for="file in ontologyOverview.files"
                  :key="file.source_file"
                  class="context-file"
                >
                  <div class="context-file-title">
                    <span>{{ file.source_file }}</span>
                    <el-tag size="small">{{ file.file_type }}</el-tag>
                  </div>
                  <p>{{ file.preview || '미리보기 없음' }}</p>
                </div>
              </div>
              <el-alert
                v-else
                type="warning"
                show-icon
                :closable="false"
                title="먼저 파일 업로드와 파싱을 완료해야 합니다."
              />
              <el-form label-position="top" class="intent-form">
                <el-form-item
                  v-for="question in ontologyQuestions"
                  :key="question.field"
                  :label="question.question"
                >
                  <el-input
                    v-model="ontologyIntentForm[question.field]"
                    type="textarea"
                    :autosize="{ minRows: 2, maxRows: 4 }"
                    :placeholder="question.placeholder"
                  />
                </el-form-item>
              </el-form>
            </template>
          </div>
          <div v-if="!ontology && !currentTaskId">
            <el-button
              type="primary"
              :loading="running || ontologyContextSaving"
              :disabled="!hasParsedFiles || !isOntologyIntentComplete"
              @click="runOntology"
            >
              온톨로지 생성 시작
            </el-button>
          </div>
          <div v-if="currentTaskId" class="mt-3">
            <ProgressPanel
              :task-id="currentTaskId"
              @completed="onOntologyCompleted"
              @failed="onTaskFailed"
            />
          </div>
          <div v-if="ontology">
            <OntologyView :ontology="ontology" />
            <div class="step-nav">
              <el-button @click="activeStep = 0" plain>← 이전</el-button>
              <el-button type="primary" @click="activeStep = 2">그래프 구축 →</el-button>
            </div>
          </div>
        </div>

        <!-- Step 2: Graph Build -->
        <div v-else-if="activeStep === 2" class="step-content">
          <h3 class="step-title">그래프 구축</h3>
          <p class="step-desc">LLM이 엔티티와 관계를 추출하여 그래프를 구축합니다.</p>
          <div v-if="!currentTaskId">
            <el-button type="primary" :loading="running" @click="runGraph">
              그래프 구축 시작
            </el-button>
            <el-button
              v-if="hasExistingGraph"
              type="success"
              :loading="running"
              @click="runGraphIncremental"
            >
              증분 업데이트 시작
            </el-button>
            <el-button @click="activeStep = 1" plain class="ml-2">← 이전</el-button>
          </div>
          <div v-if="currentTaskId" class="mt-3">
            <ProgressPanel
              :task-id="currentTaskId"
              @completed="onGraphCompleted"
              @failed="onTaskFailed"
            />
          </div>
        </div>

        <!-- Step 3: Results -->
        <div v-else-if="activeStep === 3" class="step-content results-step">
          <el-tabs v-model="resultTab" class="result-tabs">
            <el-tab-pane label="그래프 시각화" name="graph">
              <div style="height: 500px">
                <GraphView :graph-data="graphData" />
              </div>
            </el-tab-pane>
            <el-tab-pane label="채팅" name="chat">
              <div style="height: 500px">
                <ChatPanel :project-id="projectId" />
              </div>
            </el-tab-pane>
            <el-tab-pane label="시뮬레이션" name="simulation">
              <SimulationPanel
                :project-id="projectId"
                :graph-data="graphData"
                @graph-updated="onSimulationGraphUpdated"
              />
            </el-tab-pane>
            <el-tab-pane name="merge">
              <template #label>
                병합 검토
                <el-badge
                  v-if="mergeCandidateCount > 0"
                  :value="mergeCandidateCount"
                  class="merge-badge"
                />
              </template>
              <MergeReviewPanel
                :project-id="projectId"
                :graph-data="graphData"
                @merged="onMergeApplied"
              />
            </el-tab-pane>
          </el-tabs>
          <div class="step-nav">
            <el-button @click="activeStep = 2" plain>← 이전</el-button>
            <el-button type="primary" @click="activeStep = 4">Vault 내보내기 →</el-button>
          </div>
        </div>

        <!-- Step 4: Vault -->
        <div v-else-if="activeStep === 4" class="step-content">
          <h3 class="step-title">Vault 내보내기</h3>
          <p class="step-desc">Obsidian vault 파일을 확인하고 다운로드하세요.</p>
          <VaultTree
            :project-id="projectId"
            :vault-tree="vaultTree"
            @add-files="goToUpload"
          />
          <div class="step-nav">
            <el-button @click="activeStep = 3" plain>← 이전</el-button>
          </div>
        </div>
      </el-main>
    </el-container>
    <AnalysisDrawer
      v-model:visible="analysisDrawerVisible"
      :analysis-data="analysisData"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import FileUpload from '../components/FileUpload.vue'
import ProgressPanel from '../components/ProgressPanel.vue'
import OntologyView from '../components/OntologyView.vue'
import StatsPanel from '../components/StatsPanel.vue'
import GraphView from '../components/GraphView.vue'
import ChatPanel from '../components/ChatPanel.vue'
import SimulationPanel from '../components/SimulationPanel.vue'
import MergeReviewPanel from '../components/MergeReviewPanel.vue'
import { extractMergeCandidates } from '../lib/mergeCandidates.js'
import VaultTree from '../components/VaultTree.vue'
import AnalysisDrawer from '../components/AnalysisDrawer.vue'
import { projectsApi } from '../api/client.js'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.id)
const simulationOnly = computed(() => route.path.endsWith('/simulation'))

const project = ref(null)
const activeStep = ref(0)
const currentTaskId = ref(null)
const running = ref(false)
const ontology = ref(null)
const graphData = ref(null)
const stats = ref({ total_nodes: 0, total_edges: 0, nodes_by_type: {}, edges_by_type: {} })
const profileData = ref(null)
const profileTask = ref(null)
const profileRunning = ref(false)
const vaultTree = ref([])
const resultTab = ref('graph')
const mergeCandidateCount = computed(() => extractMergeCandidates(graphData.value).length)
const analysisData = ref(null)
const analysisTask = ref(null)
const analysisRunning = ref(false)
const analysisDrawerVisible = ref(false)
const ontologyContext = ref(null)
const ontologyContextLoading = ref(false)
const ontologyContextSaving = ref(false)
const ontologyIntentForm = ref({
  primary_goal: '',
  priority_focus: '',
  interpretation_policy: '',
})

const hasExistingGraph = computed(() => stats.value.total_nodes > 0)
const ontologyOverview = computed(() => ontologyContext.value?.document_overview || {})
const ontologyQuestions = computed(() => ontologyContext.value?.questions || [])
const hasParsedFiles = computed(() => (ontologyOverview.value.total_chunks || 0) > 0)
const isOntologyIntentComplete = computed(() =>
  ['primary_goal', 'priority_focus', 'interpretation_policy']
    .every(field => ontologyIntentForm.value[field]?.trim())
)

onMounted(async () => {
  try {
    const r = await projectsApi.get(projectId.value)
    project.value = r.data

    if (simulationOnly.value) {
      try {
        const gr = await projectsApi.getGraph(projectId.value)
        graphData.value = gr.data
      } catch (error) {
        console.error('Failed to load graph for simulation view:', error)
      }
      return
    }

    await loadSidebarData()
    await loadAnalysis()
    await loadOntologyContext()
    try {
      const pr = await projectsApi.getProfiles(projectId.value)
      profileData.value = pr.data
    } catch {
      // not yet generated — expected
    }

    const status = r.data.status
    if (status === 'ready') {
      try {
        const [gr, or] = await Promise.allSettled([
          projectsApi.getGraph(projectId.value),
          projectsApi.getOntology(projectId.value),
        ])
        if (gr.status === 'fulfilled') graphData.value = gr.value.data
        if (or.status === 'fulfilled') ontology.value = or.value.data
        activeStep.value = 3
      } catch {}
    } else if (status === 'building') {
      activeStep.value = 2
      try {
        const or = await projectsApi.getOntology(projectId.value)
        ontology.value = or.data
      } catch {}
    } else if (status === 'ontology') {
      activeStep.value = 1
    } else if (status === 'parsed') {
      activeStep.value = 1
    }
  } catch (e) {
    console.error('Failed to load project:', e)
  }
})

async function loadSidebarData() {
  const [statsR, vaultR] = await Promise.allSettled([
    projectsApi.getGraphStats(projectId.value),
    projectsApi.getVaultTree(projectId.value),
  ])
  if (statsR.status === 'fulfilled') stats.value = statsR.value.data
  if (vaultR.status === 'fulfilled') vaultTree.value = vaultR.value.data
}

async function loadAnalysis() {
  try {
    const r = await projectsApi.getAnalysis(projectId.value)
    analysisData.value = r.data
  } catch {
    analysisData.value = null
  }
}

function onFilesUploaded(taskId) {
  currentTaskId.value = taskId
}

async function onParseCompleted() {
  currentTaskId.value = null
  await loadOntologyContext()
  activeStep.value = 1
}

async function runOntology() {
  if (!isOntologyIntentComplete.value) {
    ElMessage.warning('온톨로지 생성 목표를 먼저 입력해 주세요.')
    return
  }
  running.value = true
  try {
    await saveOntologyContext()
    const r = await projectsApi.runOntology(projectId.value)
    currentTaskId.value = r.data.task_id
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '온톨로지 생성을 시작할 수 없습니다.')
  } finally {
    running.value = false
  }
}

async function loadOntologyContext() {
  ontologyContextLoading.value = true
  try {
    const r = await projectsApi.getOntologyContext(projectId.value)
    ontologyContext.value = r.data
    ontologyIntentForm.value = {
      primary_goal: r.data.answers?.primary_goal || '',
      priority_focus: r.data.answers?.priority_focus || '',
      interpretation_policy: r.data.answers?.interpretation_policy || '',
    }
  } catch (e) {
    ontologyContext.value = null
  } finally {
    ontologyContextLoading.value = false
  }
}

async function saveOntologyContext() {
  ontologyContextSaving.value = true
  try {
    const r = await projectsApi.saveOntologyContext(projectId.value, {
      answers: ontologyIntentForm.value,
    })
    ontologyContext.value = r.data
  } finally {
    ontologyContextSaving.value = false
  }
}

async function onOntologyCompleted() {
  currentTaskId.value = null
  try {
    const r = await projectsApi.getOntology(projectId.value)
    ontology.value = r.data
  } catch (e) {
    console.error('Failed to load ontology:', e)
  }
}

async function runGraph() {
  running.value = true
  try {
    const r = await projectsApi.runGraph(projectId.value)
    currentTaskId.value = r.data.task_id
  } finally {
    running.value = false
  }
}

async function runGraphIncremental() {
  running.value = true
  try {
    const r = await projectsApi.runGraphIncremental(projectId.value)
    currentTaskId.value = r.data.task_id
  } finally {
    running.value = false
  }
}

async function onGraphCompleted() {
  currentTaskId.value = null
  try {
    const r = await projectsApi.getGraph(projectId.value)
    graphData.value = r.data
    await loadSidebarData()
    activeStep.value = 3
  } catch (e) {
    console.error('Failed to load graph:', e)
  }
}

function onTaskFailed(err) {
  currentTaskId.value = null
  running.value = false
  ElMessage.error(err || '작업이 실패했습니다. 다시 시도해 주세요.')
}

async function onSimulationGraphUpdated(nextGraph) {
  graphData.value = nextGraph
  await loadSidebarData()
}

async function onMergeApplied() {
  try {
    const r = await projectsApi.getGraph(projectId.value)
    graphData.value = r.data
    await loadSidebarData()
  } catch (e) {
    console.error('Failed to refresh graph after merge:', e)
  }
}

function goToUpload() {
  activeStep.value = 0
}

async function runAnalysis() {
  analysisRunning.value = true
  try {
    const r = await projectsApi.runAnalysis(projectId.value)
    analysisTask.value = r.data.task_id
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '분석을 시작할 수 없습니다.')
  } finally {
    analysisRunning.value = false
  }
}

async function onAnalysisCompleted() {
  analysisTask.value = null
  try {
    const r = await projectsApi.getAnalysis(projectId.value)
    analysisData.value = r.data
    analysisDrawerVisible.value = true
  } catch {
    ElMessage.error('분석 결과를 불러오지 못했습니다.')
  }
}

function onAnalysisFailed(err) {
  analysisTask.value = null
  ElMessage.error(err || '분석에 실패했습니다.')
}

async function runProfiles() {
  profileRunning.value = true
  try {
    const r = await projectsApi.runProfiles(projectId.value)
    profileTask.value = r.data.task_id
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '프로필 생성을 시작할 수 없습니다.')
  } finally {
    profileRunning.value = false
  }
}

async function onProfileCompleted() {
  profileTask.value = null
  try {
    const r = await projectsApi.getProfiles(projectId.value)
    profileData.value = r.data
    ElMessage.success('프로필 생성이 완료됐습니다.')
  } catch {
    ElMessage.error('프로필 결과를 불러오지 못했습니다.')
  }
}

function onProfileFailed(err) {
  profileTask.value = null
  ElMessage.error(err || '프로필 생성에 실패했습니다.')
}
</script>

<style scoped>
.project-detail { background: #f5f7fa; }
.simulation-only-layout { min-height: 100vh; background: #f5f7fa; }
.simulation-only-header {
  height: 56px;
  display: flex;
  align-items: center;
  gap: 14px;
  border-bottom: 1px solid #e4e7ed;
  background: white;
}
.simulation-only-header div { display: flex; flex-direction: column; gap: 2px; }
.simulation-only-header strong { color: #303133; }
.simulation-only-header span { color: #909399; font-size: 12px; }
.simulation-only-main { padding: 18px; overflow: auto; }
.sidebar {
  border-right: 1px solid #e4e7ed;
  padding: 16px;
  overflow-y: auto;
  background: white;
  display: flex;
  flex-direction: column;
  gap: 0;
}
.sidebar-header { display: flex; flex-direction: column; gap: 4px; }
.project-title { font-size: 16px; font-weight: bold; color: #303133; padding: 4px 0; }
.sidebar-label { font-size: 11px; color: #909399; text-transform: uppercase; margin-bottom: 8px; letter-spacing: 0.5px; }
.sidebar-section { margin-bottom: 8px; }
.analysis-hint { font-size: 11px; color: #909399; margin: 6px 0 0; }
.main-panel { padding: 24px; overflow-y: auto; background: #f5f7fa; }
.steps { margin-bottom: 32px; }
.step-content { max-width: 900px; margin: 0 auto; background: white; padding: 24px; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }
.step-title { font-size: 20px; font-weight: bold; margin-bottom: 8px; color: #303133; }
.step-desc { color: #909399; margin-bottom: 20px; font-size: 14px; }
.results-step { max-width: 1100px; }
.result-tabs { height: calc(100% - 80px); }
.step-nav { display: flex; gap: 12px; margin-top: 20px; padding-top: 16px; border-top: 1px solid #f0f0f0; }
.mt-3 { margin-top: 16px; }
.ml-2 { margin-left: 8px; }
.merge-badge { margin-left: 6px; }
.ontology-context { display: flex; flex-direction: column; gap: 14px; margin-bottom: 18px; }
.context-summary {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  padding: 12px 0;
  border-top: 1px solid #ebeef5;
  border-bottom: 1px solid #ebeef5;
}
.context-label { font-size: 12px; color: #909399; margin-bottom: 4px; }
.context-files { display: grid; gap: 10px; }
.context-file { border: 1px solid #ebeef5; border-radius: 6px; padding: 10px 12px; background: #fafafa; }
.context-file-title { display: flex; justify-content: space-between; align-items: center; gap: 10px; font-size: 13px; font-weight: 600; color: #303133; }
.context-file-title span { min-width: 0; overflow-wrap: anywhere; }
.context-file p { margin: 6px 0 0; color: #606266; font-size: 12px; line-height: 1.45; }
.intent-form { margin-top: 4px; }
</style>
