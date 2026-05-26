import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import ProjectDetail from '../views/ProjectDetail.vue'
import AboutView from '../views/AboutView.vue'

const routes = [
  { path: '/', component: HomeView },
  { path: '/projects/:id', component: ProjectDetail },
  { path: '/about', component: AboutView },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
