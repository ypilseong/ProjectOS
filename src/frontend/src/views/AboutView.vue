<template>
  <div class="about">
    <el-container>
      <el-header class="about-header" height="60px">
        <el-button text @click="router.push('/')">
          <el-icon><ArrowLeft /></el-icon> 홈
        </el-button>
        <h1 class="header-title">ProjectOS 작동 원리</h1>
        <div style="width: 80px" />
      </el-header>

      <el-main class="about-main">
        <!-- sections added in next task -->
      </el-main>
    </el-container>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
const router = useRouter()
</script>

<style scoped>
.about { min-height: 100vh; background: #f5f7fa; }
.about-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 24px; background: #303133; color: white;
}
.header-title { font-size: 18px; font-weight: bold; color: white; }
.about-main { max-width: 1000px; margin: 0 auto; padding: 40px 24px; }
</style>
