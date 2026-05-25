<template>
  <div class="home">
    <el-container>
      <el-header class="header">
        <h1>ProjectOS</h1>
        <span class="subtitle">로컬 파일 → 커리어 지식 그래프</span>
      </el-header>
      <el-main>
        <el-empty description="프로젝트를 생성하세요" />
      </el-main>
    </el-container>
  </div>
</template>

<script setup>
</script>

<style scoped>
.header { display: flex; align-items: center; gap: 16px; background: #409eff; color: white; padding: 0 24px; }
.subtitle { font-size: 14px; opacity: 0.8; }
</style>
