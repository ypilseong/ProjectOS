import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import ProjectDetail from '../views/ProjectDetail.vue'

const routes = [
  { path: '/', component: HomeView },
  { path: '/projects/:id', component: ProjectDetail },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
