<template>
  <div class="home">
    <el-container>
      <el-header class="header" height="60px">
        <div class="header-left">
          <h1 class="app-title">ProjectOS</h1>
          <span class="app-subtitle">로컬 파일 → 커리어 지식 그래프</span>
        </div>
        <el-button type="primary" @click="createDialogVisible = true">
          <el-icon><Plus /></el-icon> 새 프로젝트
        </el-button>
      </el-header>

      <el-main class="main">
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
      </el-main>
    </el-container>

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
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { projectsApi } from '../api/client.js'

const router = useRouter()
const projects = ref([])
const loading = ref(true)
const creating = ref(false)
const createDialogVisible = ref(false)
const createForm = ref({ name: '', description: '' })

onMounted(loadProjects)

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
.app-title { font-size: 22px; font-weight: bold; color: white; }
.app-subtitle { font-size: 13px; opacity: 0.85; }
.main { padding: 32px; }
.project-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.project-card { cursor: pointer; transition: transform 0.15s; }
.project-card:hover { transform: translateY(-2px); }
.card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.project-name { font-size: 16px; font-weight: bold; color: #303133; }
.project-desc { font-size: 13px; color: #909399; margin-bottom: 12px; min-height: 36px; }
.card-footer { display: flex; align-items: center; justify-content: space-between; }
.stats-mini { display: flex; gap: 12px; font-size: 12px; color: #666; }
.loading { padding: 32px; }
</style>
