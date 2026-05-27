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

        <!-- 섹션 1: 시스템 아키텍처 -->
        <section class="section">
          <h2 class="section-title">시스템 아키텍처</h2>
          <p class="section-desc">4개 레이어로 구성된 풀스택 AI 파이프라인</p>
          <div class="arch-diagram">
            <div class="arch-layer layer-frontend">
              <div class="layer-header">
                <span class="layer-badge">Frontend</span>
                <span class="layer-tech">Vue 3 + Element Plus + D3.js</span>
              </div>
              <div class="layer-chips">
                <span class="chip">HomeView</span>
                <span class="chip">ProjectDetail</span>
                <span class="chip">AboutView</span>
                <span class="chip">GraphView</span>
                <span class="chip">ChatPanel</span>
                <span class="chip">VaultTree</span>
              </div>
            </div>
            <div class="arch-connector"><span class="connector-label">REST API + SSE 스트리밍</span></div>
            <div class="arch-layer layer-backend">
              <div class="layer-header">
                <span class="layer-badge">Backend</span>
                <span class="layer-tech">FastAPI + Python 3.14</span>
              </div>
              <div class="layer-chips">
                <span class="chip">/projects</span>
                <span class="chip">/graph</span>
                <span class="chip">/chat</span>
                <span class="chip">/tasks</span>
              </div>
            </div>
            <div class="arch-connector"><span class="connector-label">에이전트 파이프라인 호출</span></div>
            <div class="arch-layer layer-agents">
              <div class="layer-header">
                <span class="layer-badge">Agent Pipeline</span>
                <span class="layer-tech">OpenAI SDK + NetworkX</span>
              </div>
              <div class="layer-chips">
                <span class="chip">ParserAgent</span>
                <span class="chip">OntologyAgent</span>
                <span class="chip">GraphBuilderAgent</span>
                <span class="chip">ProfileAgent</span>
                <span class="chip">ObsidianWriterAgent</span>
                <span class="chip">QueryAgent</span>
              </div>
            </div>
            <div class="arch-connector"><span class="connector-label">읽기 / 쓰기</span></div>
            <div class="arch-layer layer-storage">
              <div class="layer-header">
                <span class="layer-badge">Storage</span>
                <span class="layer-tech">로컬 파일시스템</span>
              </div>
              <div class="layer-chips">
                <span class="chip">NetworkX DiGraph (graph.json)</span>
                <span class="chip">Obsidian Vault (Markdown)</span>
                <span class="chip">Syncthing → Mac</span>
              </div>
            </div>
          </div>
        </section>

        <!-- 섹션 2: 에이전트 파이프라인 -->
        <section class="section">
          <h2 class="section-title">에이전트 파이프라인</h2>
          <p class="section-desc">파일 업로드부터 Obsidian vault 생성까지의 데이터 흐름</p>
          <div class="pipeline-wrapper">
            <div class="pipeline-main">
              <div class="pipe-node node-input">
                <div class="node-name">파일 입력</div>
                <div class="node-io">PDF · DOCX · TXT</div>
              </div>
              <div class="pipe-arrow">→</div>
              <div class="pipe-node">
                <div class="node-name">ParserAgent</div>
                <div class="node-io">TextChunk[]</div>
              </div>
              <div class="pipe-arrow">→</div>
              <div class="pipe-node">
                <div class="node-name">OntologyAgent</div>
                <div class="node-io">Ontology</div>
              </div>
              <div class="pipe-arrow">→</div>
              <div class="pipe-node node-center">
                <div class="node-name">GraphBuilderAgent</div>
                <div class="node-io">nx.DiGraph</div>
              </div>
              <div class="pipe-arrow">→</div>
              <div class="pipe-node">
                <div class="node-name">ProfileAgent</div>
                <div class="node-io">CareerProfile[]</div>
              </div>
              <div class="pipe-arrow">→</div>
              <div class="pipe-node node-output">
                <div class="node-name">ObsidianWriterAgent</div>
                <div class="node-io">vault/ Markdown</div>
              </div>
            </div>
            <div class="pipeline-branch">
              <div class="branch-line"></div>
              <div class="pipe-node node-query">
                <div class="node-name">QueryAgent</div>
                <div class="node-io">SSE 채팅 스트리밍</div>
              </div>
            </div>
          </div>
        </section>

        <!-- 섹션 3: 5단계 사용 가이드 -->
        <section class="section">
          <h2 class="section-title">5단계 사용 가이드</h2>
          <p class="section-desc">ProjectOS를 처음 사용하는 방법</p>
          <div class="guide-grid">
            <div class="guide-card" v-for="step in steps" :key="step.num">
              <div class="step-badge">{{ step.num }}</div>
              <div class="step-content">
                <div class="step-title">{{ step.title }}</div>
                <div class="step-desc">{{ step.desc }}</div>
                <div class="step-detail">{{ step.detail }}</div>
              </div>
            </div>
          </div>
        </section>

        <!-- 섹션 4: 기술 상세 -->
        <section class="section">
          <h2 class="section-title">기술 상세</h2>
          <el-collapse>
            <el-collapse-item title="에이전트 스펙" name="agents">
              <el-table :data="agentSpecs" border size="small">
                <el-table-column prop="name" label="에이전트" width="180" />
                <el-table-column prop="input" label="입력" />
                <el-table-column prop="output" label="출력" />
                <el-table-column prop="logic" label="핵심 로직" />
              </el-table>
            </el-collapse-item>
            <el-collapse-item title="데이터 모델" name="models">
              <el-table :data="modelSpecs" border size="small">
                <el-table-column prop="name" label="모델" width="160" />
                <el-table-column prop="fields" label="주요 필드" />
              </el-table>
            </el-collapse-item>
            <el-collapse-item title="API 엔드포인트" name="api">
              <el-table :data="apiSpecs" border size="small">
                <el-table-column prop="method" label="Method" width="80" />
                <el-table-column prop="path" label="Path" width="280" />
                <el-table-column prop="desc" label="설명" />
              </el-table>
            </el-collapse-item>
          </el-collapse>
        </section>

      </el-main>
    </el-container>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'

const router = useRouter()

const steps = [
  {
    num: '1', title: '파일 업로드',
    desc: '이력서, 프로젝트 문서, 논문을 업로드합니다.',
    detail: 'PDF, DOCX, TXT 지원. 파일 타입(이력서/프로젝트/논문/노트)을 선택하면 에이전트가 맥락을 파악합니다.',
  },
  {
    num: '2', title: '온톨로지 생성',
    desc: 'LLM이 문서에서 엔티티와 관계 타입을 추출합니다.',
    detail: 'Person, Project, Skill 등 9가지 고정 엔티티 타입과 WORKED_AT, DEVELOPED 등 10가지 관계 타입을 확인할 수 있습니다. 기술 키워드, 도구, 프레임워크, 모델명은 Skill로 통합하고, 나머지 핵심 항목은 Project, Achievement 등 가장 구체적인 기존 타입으로 분류합니다.',
  },
  {
    num: '3', title: '그래프 구축',
    desc: 'NetworkX DiGraph에 노드와 엣지를 생성합니다.',
    detail: 'Fuzzy matching(유사도 0.85)으로 중복 엔티티를 자동 병합합니다. 기존 그래프에 파일을 추가하는 증분(incremental) 업데이트도 지원합니다.',
  },
  {
    num: '4', title: '결과 확인',
    desc: 'D3.js 그래프 시각화와 LLM 채팅으로 지식을 탐색합니다.',
    detail: '노드 타입별 필터링, 줌/패닝, 클릭으로 연결 정보 확인. 채팅창에서 "Python 관련 프로젝트 알려줘" 같은 자연어 질문이 가능합니다.',
  },
  {
    num: '5', title: 'Vault 내보내기',
    desc: 'Obsidian markdown으로 내보내고 Syncthing으로 Mac에 동기화합니다.',
    detail: 'YAML frontmatter, [[wikilinks]], _index.canvas 자동 생성. Syncthing 설정 시 파일 변경 즉시 Mac Obsidian에 반영됩니다.',
  },
]

const agentSpecs = [
  { name: 'ParserAgent',         input: '파일 경로[]',           output: 'TextChunk[]',     logic: 'CHUNK_SIZE=500, OVERLAP=50' },
  { name: 'OntologyAgent',       input: 'TextChunk[]',           output: 'Ontology',        logic: 'LLM chat_json, 50,000자 샘플' },
  { name: 'GraphBuilderAgent',   input: 'TextChunk[], Ontology', output: 'nx.DiGraph',      logic: 'Fuzzy dedup 0.85, incremental' },
  { name: 'ProfileAgent',        input: 'nx.DiGraph',            output: 'CareerProfile[]', logic: 'BFS 50노드, Person 기준' },
  { name: 'ObsidianWriterAgent', input: 'DiGraph, Profile[]',    output: 'vault/ Markdown', logic: 'YAML frontmatter, wikilinks, canvas' },
  { name: 'QueryAgent',          input: '질문, graph, chunks',   output: 'SSE stream',      logic: 'BFS 검색, 한국어 substring 매칭' },
]

const modelSpecs = [
  { name: 'TextChunk',     fields: 'chunk_id, text, source_file, file_type, page_num?, char_offset' },
  { name: 'Ontology',      fields: 'entity_types: EntityTypeDef[], edge_types: EdgeTypeDef[]' },
  { name: 'CareerProfile', fields: 'name, expertise[], skills[], projects[], organizations[], publications[], achievements[], persona_summary, timeline[]' },
  { name: 'GraphStats',    fields: 'total_nodes, total_edges, nodes_by_type: dict, edges_by_type: dict' },
]

const apiSpecs = [
  { method: 'POST',   path: '/projects',                     desc: '프로젝트 생성' },
  { method: 'GET',    path: '/projects',                     desc: '프로젝트 목록' },
  { method: 'DELETE', path: '/projects/{id}',                desc: '프로젝트 삭제' },
  { method: 'POST',   path: '/projects/{id}/files',          desc: '파일 업로드 → 파싱 태스크 시작' },
  { method: 'POST',   path: '/projects/{id}/ontology',       desc: '온톨로지 생성 태스크 시작' },
  { method: 'GET',    path: '/projects/{id}/ontology',       desc: '온톨로지 조회' },
  { method: 'POST',   path: '/projects/{id}/graph',          desc: '그래프 구축 태스크 시작' },
  { method: 'GET',    path: '/projects/{id}/graph',          desc: '그래프 데이터 조회' },
  { method: 'GET',    path: '/projects/{id}/graph/stats',    desc: '그래프 통계' },
  { method: 'GET',    path: '/projects/{id}/profiles',       desc: '커리어 프로필 목록' },
  { method: 'GET',    path: '/projects/{id}/vault',          desc: 'Vault 파일 트리' },
  { method: 'GET',    path: '/projects/{id}/vault/download', desc: 'Vault ZIP 다운로드' },
  { method: 'POST',   path: '/projects/{id}/chat',           desc: 'SSE 채팅 스트리밍' },
  { method: 'GET',    path: '/tasks/{id}',                   desc: '태스크 상태 조회' },
  { method: 'GET',    path: '/tasks/{id}/stream',            desc: '태스크 진행 SSE 스트림' },
]
</script>

<style scoped>
.about { min-height: 100vh; background: #f5f7fa; }
.about-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 24px; background: #303133; color: white;
}
.header-title { font-size: 18px; font-weight: bold; color: white; }
.about-main { max-width: 1000px; margin: 0 auto; padding: 40px 24px; }

.section { margin-bottom: 48px; }
.section-title { font-size: 22px; font-weight: bold; color: #303133; margin-bottom: 8px; }
.section-desc { color: #909399; font-size: 14px; margin-bottom: 24px; }

/* Architecture Diagram */
.arch-diagram { display: flex; flex-direction: column; gap: 0; max-width: 800px; }
.arch-layer {
  border-radius: 10px; padding: 16px 20px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}
.layer-frontend { background: #ecf5ff; border: 2px solid #409eff; }
.layer-backend  { background: #f0f9eb; border: 2px solid #67c23a; }
.layer-agents   { background: #fdf6ec; border: 2px solid #e6a23c; }
.layer-storage  { background: #f5f5f5; border: 2px solid #909399; }
.layer-header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.layer-badge {
  font-size: 12px; font-weight: bold; padding: 2px 10px; border-radius: 12px;
  background: white; color: #303133; border: 1px solid currentColor;
}
.layer-frontend .layer-badge { color: #409eff; }
.layer-backend .layer-badge  { color: #67c23a; }
.layer-agents .layer-badge   { color: #e6a23c; }
.layer-storage .layer-badge  { color: #909399; }
.layer-tech { font-size: 12px; color: #606266; }
.layer-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip {
  background: white; border: 1px solid #dcdfe6; border-radius: 4px;
  padding: 3px 10px; font-size: 12px; color: #606266;
}
.arch-connector {
  display: flex; align-items: center; justify-content: center;
  height: 36px; position: relative;
}
.arch-connector::before {
  content: ''; position: absolute; left: 50%; top: 0;
  width: 2px; height: 100%; background: #dcdfe6; transform: translateX(-50%);
}
.connector-label {
  background: #f5f7fa; padding: 2px 10px; font-size: 11px;
  color: #909399; border-radius: 10px; border: 1px solid #dcdfe6;
  position: relative; z-index: 1;
}

/* Pipeline Flowchart */
.pipeline-wrapper { display: flex; flex-direction: column; gap: 0; }
.pipeline-main {
  display: flex; align-items: center; gap: 4px; flex-wrap: wrap;
  background: white; border-radius: 10px; padding: 20px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06); border: 1px solid #ebeef5;
}
.pipe-node {
  background: white; border: 2px solid #e6a23c; border-radius: 8px;
  padding: 10px 14px; text-align: center; min-width: 110px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.08);
}
.node-input  { border-color: #409eff; }
.node-output { border-color: #67c23a; }
.node-query  { border-color: #9b59b6; }
.node-name { font-size: 13px; font-weight: bold; color: #303133; margin-bottom: 4px; }
.node-io { font-size: 11px; color: #909399; }
.pipe-arrow { font-size: 18px; color: #c0c4cc; flex-shrink: 0; }
.pipeline-branch {
  display: flex; align-items: center; gap: 0;
  padding-left: 20px; margin-top: 0;
}
.branch-line {
  width: 2px; height: 32px; background: #dcdfe6;
  margin-left: 468px;
}

/* User Guide */
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.guide-card {
  display: flex; gap: 16px; background: white; border-radius: 10px;
  padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); border: 1px solid #ebeef5;
}
.step-badge {
  width: 36px; height: 36px; border-radius: 50%; background: #409eff;
  color: white; font-size: 16px; font-weight: bold;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.step-content { flex: 1; }
.step-title { font-size: 15px; font-weight: bold; color: #303133; margin-bottom: 6px; }
.step-desc { font-size: 13px; color: #606266; margin-bottom: 6px; }
.step-detail { font-size: 12px; color: #909399; line-height: 1.6; }
</style>
