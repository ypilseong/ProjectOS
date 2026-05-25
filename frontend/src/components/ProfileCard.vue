<template>
  <div class="profile-card">
    <div class="profile-header">
      <el-avatar :size="48" :icon="User" />
      <div class="profile-name">{{ profile.name }}</div>
    </div>

    <div v-if="profile.expertise?.length" class="expertise-section">
      <div class="section-label">전문 분야</div>
      <div class="tag-group">
        <el-tag v-for="e in profile.expertise" :key="e" type="primary" size="small">{{ e }}</el-tag>
      </div>
    </div>

    <div v-if="profile.skills?.length" class="skills-section">
      <div class="section-label">기술 스택</div>
      <div class="tag-group">
        <el-tag v-for="s in profile.skills" :key="s" type="success" size="small">{{ s }}</el-tag>
      </div>
    </div>

    <el-collapse class="mt-2">
      <el-collapse-item v-if="profile.projects?.length" title="프로젝트" name="projects">
        <ul class="list">
          <li v-for="p in profile.projects" :key="p">{{ p }}</li>
        </ul>
      </el-collapse-item>
      <el-collapse-item v-if="profile.organizations?.length" title="소속 기관" name="orgs">
        <ul class="list">
          <li v-for="o in profile.organizations" :key="o">{{ o }}</li>
        </ul>
      </el-collapse-item>
      <el-collapse-item v-if="profile.achievements?.length" title="성과" name="achievements">
        <ul class="list">
          <li v-for="a in profile.achievements" :key="a">{{ a }}</li>
        </ul>
      </el-collapse-item>
      <el-collapse-item v-if="profile.persona_summary" title="커리어 요약" name="summary">
        <p class="summary-text">{{ profile.persona_summary }}</p>
      </el-collapse-item>
      <el-collapse-item v-if="profile.timeline?.length" title="타임라인" name="timeline">
        <el-timeline>
          <el-timeline-item
            v-for="t in profile.timeline"
            :key="t.year"
            :timestamp="String(t.year)"
            placement="top"
          >{{ t.event }}</el-timeline-item>
        </el-timeline>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup>
import { User } from '@element-plus/icons-vue'

defineProps({
  profile: {
    type: Object,
    required: true,
  },
})
</script>

<style scoped>
.profile-card { padding: 4px 0; }
.profile-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.profile-name { font-size: 18px; font-weight: bold; color: #303133; }
.section-label { font-size: 11px; color: #999; margin-bottom: 4px; text-transform: uppercase; }
.tag-group { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 8px; }
.list { padding-left: 16px; font-size: 13px; color: #444; line-height: 1.8; }
.summary-text { line-height: 1.7; color: #444; font-size: 13px; white-space: pre-wrap; }
.mt-2 { margin-top: 8px; }
</style>
