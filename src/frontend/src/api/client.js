import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

export const projectsApi = {
  list: () => api.get('/projects'),
  create: (data) => api.post('/projects', data),
  get: (id) => api.get(`/projects/${id}`),
  delete: (id) => api.delete(`/projects/${id}`),
  uploadFiles: (id, formData) => api.post(`/projects/${id}/files`, formData),
  addFiles: (id, formData) => api.post(`/projects/${id}/files/add`, formData),
  getOntology: (id) => api.get(`/projects/${id}/ontology`),
  runOntology: (id) => api.post(`/projects/${id}/ontology`),
  getGraph: (id) => api.get(`/projects/${id}/graph`),
  getGraphStats: (id) => api.get(`/projects/${id}/graph/stats`),
  runGraph: (id) => api.post(`/projects/${id}/graph`),
  runGraphIncremental: (id) => api.post(`/projects/${id}/graph/incremental`),
  getProfiles: (id) => api.get(`/projects/${id}/profiles`),
  getVaultTree: (id) => api.get(`/projects/${id}/vault`),
  downloadVault: (id) => `/api/projects/${id}/vault/download`,
  runAnalysis: (id) => api.post(`/projects/${id}/analysis`),
  getAnalysis: (id) => api.get(`/projects/${id}/analysis`),
}

export const globalApi = {
  getGraph: () => api.get('/graph/global'),
}

export const tasksApi = {
  get: (taskId) => api.get(`/tasks/${taskId}`),
  streamUrl: (taskId) => `/api/tasks/${taskId}/stream`,
}

export const chatStreamUrl = (projectId) => `/api/projects/${projectId}/chat`

export const userApi = {
  get: () => api.get('/user'),
  set: (data) => api.post('/user', data),
}

export default api
