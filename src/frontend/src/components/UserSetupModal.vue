<template>
  <el-dialog
    v-model="visible"
    title="ProjectOS에 오신 걸 환영합니다"
    width="420px"
    :close-on-click-modal="false"
    :show-close="false"
  >
    <p style="color:#606266;margin-bottom:16px">
      커리어 프로필 생성에 사용할 이름을 입력해 주세요.
    </p>
    <el-form @submit.prevent="save">
      <el-form-item label="이름 (한국어)">
        <el-input v-model="name" placeholder="예: 양필성" autofocus />
      </el-form-item>
      <el-form-item label="영문 이름">
        <el-input v-model="displayName" placeholder="예: Pilseong Yang" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button type="primary" :disabled="!name.trim()" :loading="saving" @click="save">
        시작하기
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref } from 'vue'
import { userApi } from '../api/client.js'

const visible = ref(true)
const name = ref('')
const displayName = ref('')
const saving = ref(false)

const emit = defineEmits(['saved'])

async function save() {
  if (!name.value.trim()) return
  saving.value = true
  try {
    await userApi.set({ name: name.value.trim(), display_name: displayName.value.trim() || name.value.trim() })
    visible.value = false
    emit('saved')
  } finally {
    saving.value = false
  }
}
</script>
