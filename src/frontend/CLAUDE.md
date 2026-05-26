# Frontend — ProjectOS

Vue 3 + Vite + Element Plus + D3.js.

## 명령어

```bash
# 개발 서버 (포트 5173)
npm run dev

# 프로덕션 빌드
npm run build

# 미리보기
npm run preview
```

## 디렉토리 구조

```
src/
  api/client.js      — axios 기반 API 클라이언트 (projectsApi, tasksApi, chatStreamUrl)
  components/        — 8개 재사용 컴포넌트
  views/             — 3개 페이지 뷰 (HomeView, ProjectDetail, AboutView)
  router/index.js    — Vue Router 설정
  App.vue            — 루트 컴포넌트 (router-view)
  main.js            — 앱 진입점
```

## 컴포넌트 작성 패턴

`<script setup>` Composition API 사용:

```vue
<script setup>
import { ref, computed, onMounted } from 'vue'
import { projectsApi } from '../api/client.js'

const data = ref(null)
onMounted(async () => {
  const r = await projectsApi.get(id)
  data.value = r.data
})
</script>
```

## API 클라이언트 사용법

```js
import { projectsApi, tasksApi, chatStreamUrl } from '../api/client.js'

// REST
const r = await projectsApi.list()        // GET /projects
const r = await projectsApi.create({...}) // POST /projects
const r = await projectsApi.runGraph(id)  // POST /projects/{id}/graph

// SSE — 태스크 진행 (EventSource)
const url = tasksApi.streamUrl(taskId)   // GET /tasks/{id}/stream

// SSE — 채팅 (fetch + ReadableStream)
const url = chatStreamUrl(projectId)     // POST /projects/{id}/chat
```

## SSE 수신 패턴

태스크 진행 (EventSource):
```js
const es = new EventSource(tasksApi.streamUrl(taskId))
es.onmessage = (e) => { const task = JSON.parse(e.data) }
```

채팅 스트리밍 (fetch):
```js
const res = await fetch(chatStreamUrl(projectId), { method: 'POST', body: JSON.stringify({question}) })
const reader = res.body.getReader()
// ReadableStream 읽기
```
