<template>
  <div class="file-upload">
    <el-upload
      drag
      multiple
      :auto-upload="false"
      :on-change="onFileChange"
      :file-list="fileList"
      accept=".pdf,.docx,.txt,.md"
    >
      <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
      <div class="el-upload__text">
        파일을 드래그하거나 <em>클릭하여 선택</em>
      </div>
      <template #tip>
        <div class="el-upload__tip">PDF, DOCX, TXT, MD 지원</div>
      </template>
    </el-upload>

    <div v-if="fileList.length" class="file-list">
      <div v-for="f in fileList" :key="f.uid" class="file-item">
        <el-tag :type="getFileTagType(f.name)" size="small">
          {{ getFileExt(f.name).toUpperCase() }}
        </el-tag>
        <span class="file-name">{{ f.name }}</span>
        <el-tag size="small" type="info">{{ fileTypeLabel }}</el-tag>
      </div>
    </div>

    <el-select v-model="selectedFileType" placeholder="파일 유형 선택" class="mt-2" style="width: 200px">
      <el-option label="이력서 (CV)" value="cv" />
      <el-option label="프로젝트 문서" value="project" />
      <el-option label="논문/출판물" value="publication" />
      <el-option label="기타 노트" value="note" />
    </el-select>

    <el-button
      type="primary"
      :disabled="!fileList.length"
      @click="upload"
      class="mt-2"
      style="margin-left: 8px"
    >
      업로드 및 파싱 시작
    </el-button>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { projectsApi } from '../api/client.js'

const props = defineProps({
  projectId: { type: String, required: true }
})
const emit = defineEmits(['uploaded'])

const fileList = ref([])
const selectedFileType = ref('cv')

const fileTypeLabel = computed(() => ({
  cv: '이력서',
  project: '프로젝트',
  publication: '논문',
  note: '노트'
})[selectedFileType.value])

function onFileChange(file, files) {
  fileList.value = files
}

function getFileExt(name) {
  return name.split('.').pop() || 'file'
}

function getFileTagType(name) {
  const ext = getFileExt(name)
  return { pdf: 'danger', docx: 'primary', txt: 'success', md: 'warning' }[ext] || 'info'
}

async function upload() {
  const formData = new FormData()
  fileList.value.forEach(f => formData.append('files', f.raw))
  formData.append('file_type', selectedFileType.value)
  const r = await projectsApi.uploadFiles(props.projectId, formData)
  emit('uploaded', r.data.task_id)
  fileList.value = []
}
</script>

<style scoped>
.file-upload { display: flex; flex-direction: column; gap: 8px; }
.file-list { display: flex; flex-direction: column; gap: 4px; margin-top: 8px; }
.file-item { display: flex; align-items: center; gap: 8px; padding: 4px 0; }
.file-name { flex: 1; font-size: 14px; color: #333; }
.mt-2 { margin-top: 8px; }
</style>
