<template>
  <div class="home">
    <el-container>
      <el-header class="header" height="60px">
        <div class="header-left">
          <h1 class="app-title">ProjectOS</h1>
          <span class="app-subtitle">로컬 파일 → 커리어 지식 그래프</span>
        </div>
        <div class="header-right">
          <el-button text style="color: white" @click="router.push('/about')">워크플로우</el-button>
          <el-button text style="color: white" @click="openSettings">
            <el-icon><Setting /></el-icon>
            설정
          </el-button>
          <el-button type="primary" @click="createDialogVisible = true">
            <el-icon><Plus /></el-icon> 새 프로젝트
          </el-button>
        </div>
      </el-header>

      <el-main class="main">
        <el-tabs v-model="activeTab" class="home-tabs">
          <el-tab-pane label="프로젝트 목록" name="projects">
            <div v-if="loading" class="loading">
              <el-skeleton :rows="3" animated />
            </div>

            <el-empty
              v-else-if="!projects.length"
              description="첫 프로젝트를 만들어 커리어 그래프를 시작하세요"
              :image-size="160"
            >
              <el-button type="primary" @click="createDialogVisible = true">
                프로젝트 생성
              </el-button>
            </el-empty>

            <div v-else class="project-grid">
              <el-card
                v-for="p in projects"
                :key="p.project_id"
                class="project-card"
                shadow="hover"
                @click="router.push(`/projects/${p.project_id}`)"
              >
                <div class="card-header">
                  <span class="project-name">{{ p.name }}</span>
                  <el-tag :type="statusType(p.status)" size="small">{{ statusLabel(p.status) }}</el-tag>
                </div>
                <p class="project-desc">{{ p.description || '(설명 없음)' }}</p>
                <div class="card-footer">
                  <div v-if="p.stats" class="stats-mini">
                    <span>노드 {{ p.stats.total_nodes }}</span>
                    <span>엣지 {{ p.stats.total_edges }}</span>
                  </div>
                  <div class="card-actions">
                    <el-button size="small" type="danger" text @click.stop="deleteProject(p.project_id)">
                      삭제
                    </el-button>
                  </div>
                </div>
              </el-card>
            </div>
          </el-tab-pane>

          <el-tab-pane label="전체 그래프" name="global-graph">
            <div v-if="globalGraphLoading" class="loading">
              <el-skeleton :rows="5" animated />
            </div>
            <el-empty
              v-else-if="!globalGraphData || !globalGraphData.nodes.length"
              description="그래프가 구축된 프로젝트가 없습니다. 프로젝트를 만들고 그래프를 구축하세요."
              :image-size="120"
            />
            <div v-else class="global-graph-wrapper">
              <GraphView
                :graph-data="globalGraphData"
                :project-colors="globalProjectColors"
                :project-names="globalProjectNames"
                :on-project-node-click="goToProject"
              />
            </div>
          </el-tab-pane>
        </el-tabs>
      </el-main>
    </el-container>

    <!-- User Setup Modal -->
    <UserSetupModal v-if="showUserSetup" @saved="showUserSetup = false" />

    <!-- Settings Dialog -->
    <el-dialog v-model="settingsDialogVisible" title="백엔드 설정" width="620px">
      <el-form label-position="top">
        <el-form-item label="LLM 백엔드">
          <el-radio-group v-model="settingsForm.llm_backend" class="backend-selector">
            <el-radio-button label="local">로컬 LLM</el-radio-button>
            <el-radio-button label="claude_code">Claude Code</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="그래프 빌드 모드">
          <el-radio-group v-model="settingsForm.graph_build_mode" class="backend-selector">
            <el-radio-button label="chunk">Chunk 추출</el-radio-button>
            <el-radio-button label="claude_task">Claude Task</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="settingsForm.graph_build_mode === 'chunk'" label="Chunk 추출 백엔드">
          <el-radio-group v-model="settingsForm.graph_extraction_backend" class="backend-selector">
            <el-radio-button label="local">로컬 LLM</el-radio-button>
            <el-radio-button label="claude_code">Claude Code</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="Claude Code 모델">
          <el-input
            v-model="settingsForm.claude_code_model"
            placeholder="예: claude-haiku-4-5"
            clearable
          />
        </el-form-item>
        <div class="settings-grid">
          <el-form-item label="Chunk size">
            <el-input-number v-model="settingsForm.chunk_size" :min="100" :step="100" />
          </el-form-item>
          <el-form-item label="Chunk overlap">
            <el-input-number v-model="settingsForm.chunk_overlap" :min="0" :step="10" />
          </el-form-item>
        </div>
      </el-form>
      <div class="settings-note">
        <span v-if="settingsForm.graph_build_mode === 'claude_task'">
          로컬 LLM 없이 Claude Code task runner가 격리된 <code>CLAUDE.md</code> 지시사항으로 그래프를 빌드합니다.
        </span>
        <span v-else-if="settingsForm.graph_extraction_backend === 'claude_code'">
          문서는 chunk 단위로 나누되 추출에도 <code>claude</code> CLI를 사용합니다. 모델이 느리면 chunk size를 키워 호출 수를 줄이세요.
        </span>
        <span v-else-if="settingsForm.llm_backend === 'local'">
          그래프 chunk 추출과 일반 LLM 작업에 OpenAI-compatible 로컬 엔드포인트를 사용합니다.
        </span>
        <span v-else>
          그래프 chunk 추출은 속도를 위해 로컬 LLM을 사용하고, 중복 병합과 노드 타입 검수 같은 유지보수 단계는 <code>claude</code> CLI를 사용합니다.
        </span>
      </div>
      <template #footer>
        <el-button @click="settingsDialogVisible = false">취소</el-button>
        <el-button type="primary" :loading="savingSettings" @click="saveSettings">
          저장
        </el-button>
      </template>
    </el-dialog>

    <!-- Create Project Dialog -->
    <el-dialog v-model="createDialogVisible" title="새 프로젝트" width="400px">
      <el-form :model="createForm" label-position="top">
        <el-form-item label="프로젝트 이름" required>
          <el-input v-model="createForm.name" placeholder="예: 내 커리어 그래프" />
        </el-form-item>
        <el-form-item label="설명 (선택)">
          <el-input
            v-model="createForm.description"
            type="textarea"
            :rows="2"
            placeholder="프로젝트 설명을 입력하세요"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialogVisible = false">취소</el-button>
        <el-button type="primary" :loading="creating" @click="createProject" :disabled="!createForm.name">
          생성
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Setting } from '@element-plus/icons-vue'
import GraphView from '../components/GraphView.vue'
import UserSetupModal from '../components/UserSetupModal.vue'
import { projectsApi, globalApi, userApi, settingsApi } from '../api/client.js'

const router = useRouter()
const projects = ref([])
const activeTab = ref('projects')
const globalGraphData = ref(null)
const globalGraphLoading = ref(false)
const loading = ref(true)
const creating = ref(false)
const createDialogVisible = ref(false)
const createForm = ref({ name: '', description: '' })
const showUserSetup = ref(false)
const settingsDialogVisible = ref(false)
const savingSettings = ref(false)
const defaultSettings = {
  llm_backend: 'local',
  graph_build_mode: 'chunk',
  graph_extraction_backend: 'local',
  claude_code_model: '',
  chunk_size: 500,
  chunk_overlap: 50,
}
const settingsForm = ref({ ...defaultSettings })

const globalProjectColors = computed(() => {
  if (!globalGraphData.value?.projects) return null
  return Object.fromEntries(
    globalGraphData.value.projects.map(p => [p.id, p.color])
  )
})

const globalProjectNames = computed(() => {
  if (!globalGraphData.value?.projects) return null
  return Object.fromEntries(
    globalGraphData.value.projects.map(p => [p.id, p.name])
  )
})

onMounted(async () => {
  try {
    await userApi.get()
  } catch {
    showUserSetup.value = true
  }
  await loadSettings()
  await loadProjects()
})

watch(activeTab, async (tab) => {
  if (tab === 'global-graph' && !globalGraphData.value) {
    await loadGlobalGraph()
  }
})

async function loadProjects() {
  loading.value = true
  try {
    const r = await projectsApi.list()
    projects.value = r.data
  } catch {
    projects.value = []
  } finally {
    loading.value = false
  }
}

async function createProject() {
  if (!createForm.value.name.trim()) return
  creating.value = true
  try {
    const r = await projectsApi.create({
      name: createForm.value.name.trim(),
      description: createForm.value.description.trim(),
    })
    createDialogVisible.value = false
    createForm.value = { name: '', description: '' }
    router.push(`/projects/${r.data.project_id}`)
  } catch (e) {
    ElMessage.error('프로젝트 생성에 실패했습니다.')
  } finally {
    creating.value = false
  }
}

async function loadSettings() {
  try {
    const r = await settingsApi.get()
    settingsForm.value = { ...defaultSettings, ...r.data }
  } catch {
    settingsForm.value = { ...defaultSettings }
  }
}

async function openSettings() {
  await loadSettings()
  settingsDialogVisible.value = true
}

async function saveSettings() {
  savingSettings.value = true
  try {
    const r = await settingsApi.set(settingsForm.value)
    settingsForm.value = { ...defaultSettings, ...r.data }
    settingsDialogVisible.value = false
    ElMessage.success('백엔드 설정을 저장했습니다.')
  } catch {
    ElMessage.error('백엔드 설정 저장에 실패했습니다.')
  } finally {
    savingSettings.value = false
  }
}

async function deleteProject(id) {
  try {
    await ElMessageBox.confirm('프로젝트를 삭제하시겠습니까?', '확인', { type: 'warning' })
  } catch {
    return
  }
  try {
    await projectsApi.delete(id)
    await loadProjects()
  } catch {
    ElMessage.error('삭제에 실패했습니다.')
  }
}

async function loadGlobalGraph() {
  globalGraphLoading.value = true
  try {
    const r = await globalApi.getGraph()
    globalGraphData.value = r.data
  } catch {
    globalGraphData.value = { nodes: [], links: [], projects: [] }
  } finally {
    globalGraphLoading.value = false
  }
}

function goToProject(projectId) {
  router.push(`/projects/${projectId}`)
}

function statusLabel(s) {
  return { created: '생성됨', parsing: '파싱 중', ontology: '온톨로지', building: '구축 중', writing: '작성 중', ready: '완료', failed: '실패' }[s] || s
}

function statusType(s) {
  return { ready: 'success', failed: 'danger', building: 'warning', parsing: 'warning' }[s] || 'info'
}
</script>

<style scoped>
.home { min-height: 100vh; background: #f5f7fa; }
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: #409eff;
  color: white;
}
.header-left { display: flex; align-items: center; gap: 16px; }
.header-right { display: flex; align-items: center; gap: 8px; }
.app-title { font-size: 22px; font-weight: bold; color: white; }
.app-subtitle { font-size: 13px; opacity: 0.85; }
.main { padding: 32px; }
.home-tabs { width: 100%; }
.global-graph-wrapper { height: 600px; }
.project-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.project-card { cursor: pointer; transition: transform 0.15s; }
.project-card:hover { transform: translateY(-2px); }
.card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.project-name { font-size: 16px; font-weight: bold; color: #303133; }
.project-desc { font-size: 13px; color: #909399; margin-bottom: 12px; min-height: 36px; }
.card-footer { display: flex; align-items: center; justify-content: space-between; }
.stats-mini { display: flex; gap: 12px; font-size: 12px; color: #666; }
.loading { padding: 32px; }
.backend-selector { width: 100%; }
.backend-selector :deep(.el-radio-button) { flex: 1; }
.backend-selector :deep(.el-radio-button__inner) { width: 100%; }
.settings-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.settings-grid :deep(.el-input-number) { width: 100%; }
.settings-note {
  margin-top: -4px;
  color: #606266;
  font-size: 13px;
  line-height: 1.5;
}
.settings-note code {
  padding: 1px 4px;
  border-radius: 4px;
  background: #f0f2f5;
  color: #303133;
}
</style>
