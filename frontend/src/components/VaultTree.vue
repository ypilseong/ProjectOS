<template>
  <div class="vault-tree">
    <div class="vault-actions">
      <el-button size="small" type="primary" @click="downloadZip">
        <el-icon><Download /></el-icon>
        ZIP 다운로드
      </el-button>
      <el-button size="small" @click="emit('add-files')">
        <el-icon><Plus /></el-icon>
        파일 추가 (증분)
      </el-button>
    </div>

    <div v-if="!vaultTree.length" class="empty-vault">
      <el-empty description="Vault가 비어있습니다" :image-size="80" />
    </div>
    <el-tree
      v-else
      :data="vaultTree"
      :props="treeProps"
      @node-click="onNodeClick"
      highlight-current
      node-key="name"
      default-expand-all
    >
      <template #default="{ node, data }">
        <span class="tree-node">
          <el-icon v-if="data.type === 'folder'"><Folder /></el-icon>
          <el-icon v-else><Document /></el-icon>
          <span class="node-label">{{ node.label }}</span>
          <el-tag v-if="data.type === 'file'" size="small" type="info" class="file-ext">
            {{ getExt(data.name) }}
          </el-tag>
        </span>
      </template>
    </el-tree>

    <el-drawer
      v-model="previewVisible"
      direction="rtl"
      size="50%"
      :title="previewTitle"
    >
      <div class="preview-wrapper">
        <pre class="preview-content">{{ previewContent }}</pre>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { projectsApi } from '../api/client.js'

const props = defineProps({
  projectId: { type: String, required: true },
  vaultTree: { type: Array, default: () => [] },
})
const emit = defineEmits(['add-files'])

const previewVisible = ref(false)
const previewTitle = ref('')
const previewContent = ref('')
const treeProps = { label: 'name', children: 'children' }

async function onNodeClick(data) {
  if (data.type === 'file' && (data.name.endsWith('.md') || data.name.endsWith('.canvas'))) {
    previewTitle.value = data.name
    try {
      const resp = await fetch(
        `/api/projects/${props.projectId}/vault/file?path=${encodeURIComponent(data.path || data.name)}`
      )
      if (resp.ok) {
        previewContent.value = await resp.text()
      } else {
        previewContent.value = '(미리보기를 불러올 수 없습니다)'
      }
    } catch {
      previewContent.value = '(미리보기 오류)'
    }
    previewVisible.value = true
  }
}

function downloadZip() {
  window.open(projectsApi.downloadVault(props.projectId))
}

function getExt(name) {
  const parts = name.split('.')
  return parts.length > 1 ? parts.pop().toUpperCase() : 'FILE'
}
</script>

<style scoped>
.vault-tree { padding: 4px 0; }
.vault-actions { display: flex; gap: 8px; margin-bottom: 12px; }
.empty-vault { text-align: center; padding: 16px 0; }
.tree-node { display: flex; align-items: center; gap: 6px; font-size: 13px; }
.node-label { flex: 1; }
.file-ext { font-size: 10px; }
.preview-wrapper { height: 100%; overflow-y: auto; padding: 8px; }
.preview-content {
  white-space: pre-wrap;
  font-family: 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.6;
  color: #333;
}
</style>
