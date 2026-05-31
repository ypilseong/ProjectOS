# Obsidian Plugin Svelte Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the ProjectOS Obsidian side-panel view in Svelte 5 with a dynamic, theme-adaptive UI while preserving every existing feature 1:1.

**Architecture:** Only the side-panel `ItemView` becomes a Svelte app mounted into the view container. The settings tab stays native Obsidian `Setting` API. API calls, runtime presets, vault helpers, and shared state move into pure TS modules so logic stays unit-testable; `.svelte` components stay thin.

**Tech Stack:** TypeScript, Svelte 5 (runes), esbuild + esbuild-svelte, Obsidian API, node:test (tsx).

**Spec:** `docs/superpowers/specs/2026-05-31-obsidian-plugin-svelte-redesign-design.md`

**Reference:** The current `src/obsidian-plugin/main.ts` (1180 lines) is the behavior source of truth. Port against it; do not change behavior.

---

## File Structure

All paths are under `src/obsidian-plugin/`.

```
src/main.ts                     Plugin entry: Plugin, ItemView (mount/unmount Svelte), SettingTab (native, ported as-is)
src/api/types.ts                Shared TS interfaces
src/api/client.ts               ApiClient class: all fetch + SSE wrappers
src/lib/vaultSync.ts            MOVED from ./vaultSync.ts (unchanged content)
src/lib/runtime.ts              RUNTIME_PRESETS, mergeBackendSettings, matchRuntimePreset, parsePositiveInt, DEFAULT_BACKEND_SETTINGS
src/lib/graphColors.ts          GRAPH_COLOR_GROUPS, ensureGraphColorGroups, clearGenerated, writePayloadToVault
src/store/appStore.svelte.ts    AppStore runes class (shared state + actions)
src/ui/Card.svelte
src/ui/Button.svelte
src/ui/StatusPill.svelte
src/ui/ProgressBar.svelte
src/ui/Disclosure.svelte
src/ui/Tabs.svelte
src/sections/ProjectSection.svelte
src/sections/RuntimeSection.svelte
src/sections/SyncSection.svelte
src/sections/CollectSection.svelte
src/sections/AnalysisSection.svelte
src/sections/SimulationSection.svelte
src/sections/QuerySection.svelte
src/App.svelte                  Header (title + status + progress) + 7 sections
tests/vaultSync.test.ts         Existing — import path updated
tests/runtime.test.ts           New — runtime helpers
styles.css                      Rewritten: Obsidian CSS vars + animations
esbuild.config.mjs              + esbuild-svelte, entry src/main.ts
tsconfig.json                   include src/**/*, svelte types
package.json                    + svelte, esbuild-svelte, svelte-preprocess
```

The old `main.ts` and `vaultSync.ts` at the plugin root are removed in the final task.

---

## Task 1: Add Svelte build dependencies

**Files:**
- Modify: `src/obsidian-plugin/package.json`

- [ ] **Step 1: Install dev dependencies**

Run from `src/obsidian-plugin/`:
```bash
npm install --save-dev svelte@^5.0.0 esbuild-svelte@^0.8.1 svelte-preprocess@^6.0.0
```
Expected: packages added to `devDependencies`, `package-lock.json` updated, no errors.

- [ ] **Step 2: Verify Svelte resolves**

Run: `node -e "import('svelte/compiler').then(()=>console.log('ok'))"`
Expected: prints `ok`.

- [ ] **Step 3: Commit**

```bash
git add src/obsidian-plugin/package.json src/obsidian-plugin/package-lock.json
git commit -m "build: add svelte and esbuild-svelte deps to obsidian plugin"
```

---

## Task 2: Wire esbuild-svelte and move entry point

**Files:**
- Modify: `src/obsidian-plugin/esbuild.config.mjs`
- Modify: `src/obsidian-plugin/tsconfig.json`

- [ ] **Step 1: Update esbuild config**

Replace the whole `src/obsidian-plugin/esbuild.config.mjs` with:
```js
import esbuild from "esbuild";
import process from "process";
import builtins from "builtin-modules";
import esbuildSvelte from "esbuild-svelte";
import { sveltePreprocess } from "svelte-preprocess";

const prod = process.argv[2] === "production";

const context = await esbuild.context({
  banner: {
    js: "/* ProjectOS Vault Sync */",
  },
  bundle: true,
  entryPoints: ["src/main.ts"],
  external: [
    "obsidian",
    "electron",
    "@codemirror/autocomplete",
    "@codemirror/collab",
    "@codemirror/commands",
    "@codemirror/language",
    "@codemirror/lint",
    "@codemirror/search",
    "@codemirror/state",
    "@codemirror/view",
    "@lezer/common",
    "@lezer/highlight",
    "@lezer/lr",
    ...builtins,
  ],
  plugins: [
    esbuildSvelte({
      compilerOptions: { css: "injected" },
      preprocess: sveltePreprocess(),
    }),
  ],
  format: "cjs",
  logLevel: "info",
  minify: prod,
  outfile: "main.js",
  platform: "browser",
  sourcemap: prod ? false : "inline",
  target: "es2018",
  treeShaking: true,
  mainFields: ["svelte", "browser", "module", "main"],
  conditions: ["svelte", "browser"],
});

if (prod) {
  await context.rebuild();
  await context.dispose();
} else {
  await context.watch();
}
```

- [ ] **Step 2: Update tsconfig**

Replace `src/obsidian-plugin/tsconfig.json` with:
```json
{
  "compilerOptions": {
    "baseUrl": ".",
    "inlineSourceMap": true,
    "inlineSources": true,
    "lib": ["DOM", "ES2021"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "target": "ES2021",
    "allowSyntheticDefaultImports": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "verbatimModuleSyntax": false,
    "types": ["svelte"]
  },
  "include": ["src/**/*.ts", "src/**/*.svelte"]
}
```

- [ ] **Step 3: Create a temporary smoke entry to verify build**

Create `src/obsidian-plugin/src/main.ts` with a minimal stub (replaced in Task 12):
```ts
import { Plugin } from "obsidian";

export default class ProjectOSPlugin extends Plugin {
  async onload(): Promise<void> {
    console.log("ProjectOS plugin loaded");
  }
}
```

Create `src/obsidian-plugin/src/App.svelte`:
```svelte
<script lang="ts">
  let { name = "ProjectOS" }: { name?: string } = $props();
</script>

<h2>{name}</h2>
```

- [ ] **Step 4: Run production build**

Run from `src/obsidian-plugin/`: `npm run build`
Expected: build succeeds, `main.js` regenerated, no errors. (App.svelte unused is fine.)

- [ ] **Step 5: Commit**

```bash
git add src/obsidian-plugin/esbuild.config.mjs src/obsidian-plugin/tsconfig.json src/obsidian-plugin/src/main.ts src/obsidian-plugin/src/App.svelte
git commit -m "build: wire esbuild-svelte and move entry to src/"
```

---

## Task 3: Move vaultSync into lib and fix test import

**Files:**
- Create: `src/obsidian-plugin/src/lib/vaultSync.ts` (moved)
- Delete: `src/obsidian-plugin/vaultSync.ts`
- Modify: `src/obsidian-plugin/tests/vaultSync.test.ts`

- [ ] **Step 1: Move the file**

Run from `src/obsidian-plugin/`:
```bash
mkdir -p src/lib && git mv vaultSync.ts src/lib/vaultSync.ts
```

- [ ] **Step 2: Update the test import**

In `src/obsidian-plugin/tests/vaultSync.test.ts`, change the import line:
```ts
import { buildVaultSyncPlan, joinVaultPath, type VaultPayload } from "../src/lib/vaultSync";
```

- [ ] **Step 3: Run the existing test**

Run: `npm test`
Expected: vaultSync tests PASS.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: move vaultSync to src/lib and fix test import"
```

---

## Task 4: Extract runtime helpers (TDD)

**Files:**
- Create: `src/obsidian-plugin/src/lib/runtime.ts`
- Create: `src/obsidian-plugin/tests/runtime.test.ts`

- [ ] **Step 1: Write the failing test**

Create `src/obsidian-plugin/tests/runtime.test.ts`:
```ts
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  DEFAULT_BACKEND_SETTINGS,
  RUNTIME_PRESETS,
  mergeBackendSettings,
  matchRuntimePreset,
  parsePositiveInt,
} from "../src/lib/runtime";

test("parsePositiveInt returns parsed value or fallback", () => {
  assert.equal(parsePositiveInt("1800", 500), 1800);
  assert.equal(parsePositiveInt("abc", 500), 500);
  assert.equal(parsePositiveInt("-5", 500), 500);
});

test("mergeBackendSettings fills defaults", () => {
  const merged = mergeBackendSettings({ llm_backend: "claude_code" });
  assert.equal(merged.llm_backend, "claude_code");
  assert.equal(merged.chunk_size, DEFAULT_BACKEND_SETTINGS.chunk_size);
});

test("matchRuntimePreset finds the local preset", () => {
  const settings = mergeBackendSettings(
    RUNTIME_PRESETS.find((p) => p.id === "local")!.settings,
  );
  assert.equal(matchRuntimePreset(settings), "local");
});

test("matchRuntimePreset returns null for custom settings", () => {
  const settings = mergeBackendSettings({
    llm_backend: "local",
    graph_build_mode: "claude_task",
    graph_extraction_backend: "local",
  });
  assert.equal(matchRuntimePreset(settings), null);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test`
Expected: FAIL — cannot find module `../src/lib/runtime`.

- [ ] **Step 3: Write the implementation**

Create `src/obsidian-plugin/src/lib/runtime.ts`:
```ts
export interface BackendSettings {
  llm_backend: string;
  graph_build_mode: string;
  graph_extraction_backend: string;
  claude_code_model: string;
  chunk_size: number;
  chunk_overlap: number;
}

export const DEFAULT_BACKEND_SETTINGS: BackendSettings = {
  llm_backend: "local",
  graph_build_mode: "chunk",
  graph_extraction_backend: "local",
  claude_code_model: "",
  chunk_size: 500,
  chunk_overlap: 50,
};

export const RUNTIME_PRESETS: Array<{
  id: string;
  title: string;
  description: string;
  settings: Partial<BackendSettings>;
}> = [
  {
    id: "local",
    title: "Local",
    description: "Use the local OpenAI-compatible endpoint for graph extraction.",
    settings: {
      llm_backend: "local",
      graph_build_mode: "chunk",
      graph_extraction_backend: "local",
    },
  },
  {
    id: "hybrid",
    title: "Hybrid",
    description: "Use local extraction and Claude Code for higher quality maintenance.",
    settings: {
      llm_backend: "claude_code",
      graph_build_mode: "chunk",
      graph_extraction_backend: "local",
    },
  },
  {
    id: "claude_task",
    title: "Claude Task",
    description: "Run graph build through the isolated Claude Code task flow.",
    settings: {
      llm_backend: "claude_code",
      graph_build_mode: "claude_task",
      graph_extraction_backend: "claude_code",
      claude_code_model: "claude-haiku-4-5",
      chunk_size: 1800,
      chunk_overlap: 150,
    },
  },
];

export function mergeBackendSettings(settings: Partial<BackendSettings>): BackendSettings {
  return { ...DEFAULT_BACKEND_SETTINGS, ...settings };
}

export function parsePositiveInt(value: string, fallback: number): number {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

export function matchRuntimePreset(settings: BackendSettings): string | null {
  for (const preset of RUNTIME_PRESETS) {
    const merged = mergeBackendSettings(preset.settings);
    if (
      merged.llm_backend === settings.llm_backend &&
      merged.graph_build_mode === settings.graph_build_mode &&
      merged.graph_extraction_backend === settings.graph_extraction_backend
    ) {
      return preset.id;
    }
  }
  return null;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test`
Expected: all runtime + vaultSync tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/obsidian-plugin/src/lib/runtime.ts src/obsidian-plugin/tests/runtime.test.ts
git commit -m "refactor: extract runtime preset helpers with tests"
```

---

## Task 5: Extract graph color / vault write helpers (TDD)

**Files:**
- Create: `src/obsidian-plugin/src/lib/graphColors.ts`
- Create: `src/obsidian-plugin/tests/graphColors.test.ts`

- [ ] **Step 1: Write the failing test**

Create `src/obsidian-plugin/tests/graphColors.test.ts`:
```ts
import assert from "node:assert/strict";
import { test } from "node:test";

import { GRAPH_COLOR_GROUPS, buildColorGroups } from "../src/lib/graphColors";

test("GRAPH_COLOR_GROUPS covers the ten entity tags", () => {
  const tags = GRAPH_COLOR_GROUPS.map(([tag]) => tag);
  assert.deepEqual(tags, [
    "person", "project", "skill", "organization", "publication",
    "role", "achievement", "event", "institution", "category",
  ]);
});

test("buildColorGroups preserves unmanaged groups and replaces managed ones", () => {
  const existing = [
    { query: "tag:#custom", color: { a: 1, rgb: 1 } },
    { query: "tag:#person", color: { a: 1, rgb: 999 } },
  ];
  const result = buildColorGroups(existing);
  const custom = result.find((g) => g.query === "tag:#custom");
  const person = result.filter((g) => g.query === "tag:#person");
  assert.ok(custom, "keeps custom group");
  assert.equal(person.length, 1, "exactly one person group");
  assert.equal(person[0].color.rgb, 0x4895ef, "person uses managed color");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test`
Expected: FAIL — cannot find module `../src/lib/graphColors`.

- [ ] **Step 3: Write the implementation**

Create `src/obsidian-plugin/src/lib/graphColors.ts`:
```ts
import { App, TFile } from "obsidian";

import { GENERATED_FOLDERS, buildVaultSyncPlan, type VaultPayload } from "./vaultSync";

export const GRAPH_COLOR_GROUPS = [
  ["person", 0x4895ef],
  ["project", 0x2a9d8f],
  ["skill", 0xf4a261],
  ["organization", 0x9b5de5],
  ["publication", 0xe76f51],
  ["role", 0x00b4d8],
  ["achievement", 0xf9c74f],
  ["event", 0x90be6d],
  ["institution", 0xf72585],
  ["category", 0x8d99ae],
] as const;

interface ColorGroup {
  query: string;
  color: { a: number; rgb: number };
}

export function buildColorGroups(existing: unknown): ColorGroup[] {
  const existingGroups = Array.isArray(existing) ? existing : [];
  const managedQueries = new Set(GRAPH_COLOR_GROUPS.map(([tag]) => `tag:#${tag}`));
  return [
    ...existingGroups.filter((group) => {
      if (!group || typeof group !== "object") return true;
      const query = (group as { query?: unknown }).query;
      return typeof query !== "string" || !managedQueries.has(query);
    }),
    ...GRAPH_COLOR_GROUPS.map(([tag, rgb]) => ({
      query: `tag:#${tag}`,
      color: { a: 1, rgb },
    })),
  ];
}

async function ensureFolder(app: App, path: string): Promise<void> {
  if (!path) return;
  const segments = path.split("/").filter(Boolean);
  let current = "";
  for (const segment of segments) {
    current = current ? `${current}/${segment}` : segment;
    if (!(await app.vault.adapter.exists(current))) {
      await app.vault.createFolder(current);
    }
  }
}

async function writeText(app: App, path: string, content: string): Promise<void> {
  const parent = path.split("/").slice(0, -1).join("/");
  await ensureFolder(app, parent);
  const existing = app.vault.getAbstractFileByPath(path);
  if (existing instanceof TFile) {
    await app.vault.modify(existing, content);
  } else {
    await app.vault.create(path, content);
  }
}

async function ensureGraphColorGroups(app: App): Promise<void> {
  const path = ".obsidian/graph.json";
  let config: Record<string, unknown> = {};
  if (await app.vault.adapter.exists(path)) {
    try {
      config = JSON.parse(await app.vault.adapter.read(path)) as Record<string, unknown>;
    } catch {
      config = {};
    }
  }
  config.colorGroups = buildColorGroups(config.colorGroups);
  await writeText(app, path, JSON.stringify(config, null, 2));
}

async function clearGenerated(app: App, targetFolder: string): Promise<void> {
  for (const folder of GENERATED_FOLDERS) {
    const path = [targetFolder, folder]
      .map((part) => part.trim().replace(/^\/+|\/+$/g, ""))
      .filter(Boolean)
      .join("/");
    if (await app.vault.adapter.exists(path)) {
      await app.vault.adapter.rmdir(path, true);
    }
  }
}

export async function writePayloadToVault(
  app: App,
  payload: VaultPayload,
  targetFolder: string,
): Promise<number> {
  const plan = buildVaultSyncPlan(payload, targetFolder);
  await clearGenerated(app, targetFolder);
  for (const write of plan.writes) {
    await writeText(app, write.path, write.content);
  }
  await ensureGraphColorGroups(app);
  return plan.noteCount;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test`
Expected: all tests PASS. (The test imports only `GRAPH_COLOR_GROUPS` and `buildColorGroups`, which are pure; `obsidian` import is not exercised at test time because node only resolves the used exports' module graph — if node errors on the `obsidian` import, split pure helpers: see note.)

Note: if `npm test` fails resolving `obsidian`, move `GRAPH_COLOR_GROUPS` + `buildColorGroups` into `src/lib/graphColorGroups.ts` (no obsidian import) and re-export from `graphColors.ts`; update the test import to `../src/lib/graphColorGroups`. Then re-run `npm test` (PASS).

- [ ] **Step 5: Commit**

```bash
git add src/obsidian-plugin/src/lib/graphColors.ts src/obsidian-plugin/tests/graphColors.test.ts
git commit -m "refactor: extract graph color and vault write helpers with tests"
```

---

## Task 6: API types and client

**Files:**
- Create: `src/obsidian-plugin/src/api/types.ts`
- Create: `src/obsidian-plugin/src/api/client.ts`

- [ ] **Step 1: Create types**

Create `src/obsidian-plugin/src/api/types.ts`:
```ts
export interface ProjectSummary {
  project_id: string;
  name: string;
  description?: string;
  status?: string;
}

export interface TaskUpdate {
  progress?: number;
  message?: string;
  status?: string;
}

export interface AnalysisResult {
  summary?: string;
  generated_at?: string;
  issues?: Array<{ severity?: string; category?: string; description?: string; suggestion?: string }>;
  improved_draft?: string;
}

export interface SimulationResult {
  personas?: Array<{ agent_id?: string; name?: string; role?: string; goals?: string[]; knowledge?: string[] }>;
  environment?: { objective?: string; rules?: string[]; constraints?: string[] };
  timeline?: Array<{ round?: number; agent_id?: string; observation?: string; proposal?: string }>;
  applied_graph_changes?: { nodes_added?: number; edges_added?: number };
  cv_improvements?: { summary?: string; improved_draft?: string; bullets?: string[] };
  report?: { title?: string; answer?: string; recommendations?: string[]; evidence?: string[] };
}
```

- [ ] **Step 2: Create the client**

Create `src/obsidian-plugin/src/api/client.ts`:
```ts
import { BackendSettings, mergeBackendSettings } from "../lib/runtime";
import { AnalysisResult, ProjectSummary, SimulationResult, TaskUpdate } from "./types";
import type { VaultPayload } from "../lib/vaultSync";

export class ApiClient {
  constructor(private getBaseUrl: () => string) {}

  private url(path: string): string {
    return `${this.getBaseUrl().replace(/\/+$/, "")}${path}`;
  }

  private async json<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(this.url(path), init);
    if (!response.ok) throw new Error(await response.text());
    return (await response.json()) as T;
  }

  listProjects(): Promise<ProjectSummary[]> {
    return this.json<ProjectSummary[]>("/api/projects");
  }

  createProject(name: string): Promise<ProjectSummary> {
    return this.json<ProjectSummary>("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, description: "Created from Obsidian" }),
    });
  }

  async getBackendSettings(): Promise<BackendSettings> {
    return mergeBackendSettings(await this.json<Partial<BackendSettings>>("/api/settings"));
  }

  async setBackendSettings(settings: BackendSettings): Promise<BackendSettings> {
    return mergeBackendSettings(
      await this.json<Partial<BackendSettings>>("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      }),
    );
  }

  exportVault(projectId: string): Promise<VaultPayload> {
    return this.json<VaultPayload>(`/api/projects/${projectId}/vault/export`);
  }

  async uploadFiles(projectId: string, files: FileList): Promise<void> {
    const form = new FormData();
    Array.from(files).forEach((file) => form.append("files", file));
    form.append("file_type", "note");
    const response = await fetch(this.url(`/api/projects/${projectId}/files`), {
      method: "POST",
      body: form,
    });
    if (!response.ok) throw new Error(await response.text());
  }

  startGraphBuild(projectId: string): Promise<{ task_id: string }> {
    return this.json<{ task_id: string }>(`/api/projects/${projectId}/graph`, { method: "POST" });
  }

  startAnalysis(projectId: string): Promise<{ task_id: string }> {
    return this.json<{ task_id: string }>(`/api/projects/${projectId}/analysis`, { method: "POST" });
  }

  getAnalysis(projectId: string): Promise<AnalysisResult> {
    return this.json<AnalysisResult>(`/api/projects/${projectId}/analysis`);
  }

  startSimulation(projectId: string, query: string): Promise<{ task_id: string }> {
    return this.json<{ task_id: string }>(`/api/projects/${projectId}/simulation`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: query.trim(), apply_graph: true, update_vault: true }),
    });
  }

  getSimulation(projectId: string): Promise<SimulationResult> {
    return this.json<SimulationResult>(`/api/projects/${projectId}/simulation`);
  }

  watchTask(
    taskId: string,
    onUpdate: (data: TaskUpdate) => void,
    onDone: (status: string) => void,
    onError: () => void,
  ): EventSource {
    const events = new EventSource(this.url(`/api/tasks/${taskId}/stream`));
    events.onmessage = (event) => {
      const data = JSON.parse(event.data) as TaskUpdate;
      onUpdate(data);
      if (data.status === "completed" || data.status === "failed") {
        events.close();
        onDone(data.status);
      }
    };
    events.onerror = () => {
      events.close();
      onError();
    };
    return events;
  }

  async streamChat(projectId: string, question: string, onToken: (token: string) => void): Promise<void> {
    const response = await fetch(this.url(`/api/projects/${projectId}/chat`), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    if (!response.ok || !response.body) throw new Error(await response.text());
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop() ?? "";
      for (const event of events) {
        const line = event.split("\n").find((part) => part.startsWith("data: "));
        if (!line) continue;
        const data = JSON.parse(line.slice(6));
        if (data.token) onToken(data.token);
      }
    }
  }
}
```

- [ ] **Step 3: Build to typecheck**

Run: `npm run build`
Expected: build succeeds (modules compile, even though unused so far).

- [ ] **Step 4: Commit**

```bash
git add src/obsidian-plugin/src/api/types.ts src/obsidian-plugin/src/api/client.ts
git commit -m "feat: add api client and shared types for plugin"
```

---

## Task 7: App store (runes)

**Files:**
- Create: `src/obsidian-plugin/src/store/appStore.svelte.ts`

- [ ] **Step 1: Create the store**

Create `src/obsidian-plugin/src/store/appStore.svelte.ts`:
```ts
import { Notice } from "obsidian";

import { ApiClient } from "../api/client";
import { AnalysisResult, ProjectSummary, SimulationResult, TaskUpdate } from "../api/types";
import { BackendSettings, DEFAULT_BACKEND_SETTINGS, mergeBackendSettings } from "../lib/runtime";

export interface PluginBridge {
  settings: { baseUrl: string; projectId: string; projectName: string; targetFolder: string };
  saveSettings(): Promise<void>;
}

export class AppStore {
  status = $state("Idle");
  task = $state<TaskUpdate | null>(null);
  projects = $state<ProjectSummary[]>([]);
  backendSettings = $state<BackendSettings>({ ...DEFAULT_BACKEND_SETTINGS });
  runtimeDirty = $state(false);
  analysis = $state<AnalysisResult | null>(null);
  simulation = $state<SimulationResult | null>(null);
  simulationLive = $state("");
  answer = $state("");

  constructor(
    public client: ApiClient,
    public plugin: PluginBridge,
  ) {}

  get projectId(): string {
    return this.plugin.settings.projectId.trim();
  }

  requireProjectId(): string | null {
    if (!this.projectId) {
      new Notice("Create or select a ProjectOS project first.");
      return null;
    }
    return this.projectId;
  }

  targetFolder(): string {
    const explicit = this.plugin.settings.targetFolder.trim();
    if (explicit) return explicit;
    const name = this.plugin.settings.projectName.trim() || this.projectId;
    return name ? `ProjectOS/${name}` : "ProjectOS";
  }

  private fail(message: string, error: unknown): void {
    this.status = message;
    new Notice(`${message} ${String(error)}`);
  }

  async refreshProjects(): Promise<void> {
    this.status = "Loading projects...";
    try {
      this.projects = await this.client.listProjects();
      this.status = this.projects.length ? "Projects loaded." : "No projects yet.";
    } catch (error) {
      this.projects = [];
      this.fail("Project list failed.", error);
    }
  }

  async selectProject(projectId: string): Promise<void> {
    if (!projectId) return;
    const match = this.projects.find((p) => p.project_id === projectId);
    this.plugin.settings.projectId = projectId;
    this.plugin.settings.projectName = match?.name ?? projectId;
    await this.plugin.saveSettings();
    this.status = `Selected ${this.plugin.settings.projectName}.`;
  }

  async createProject(name: string): Promise<void> {
    this.status = "Creating project...";
    try {
      const project = await this.client.createProject(name.trim() || "Obsidian Project");
      this.plugin.settings.projectId = project.project_id;
      this.plugin.settings.projectName = project.name;
      await this.plugin.saveSettings();
      await this.refreshProjects();
      this.status = `Created ${project.name}.`;
      new Notice(`ProjectOS project created: ${project.name}`);
    } catch (error) {
      this.fail("Project create failed.", error);
    }
  }

  async loadBackendSettings(): Promise<void> {
    try {
      this.backendSettings = await this.client.getBackendSettings();
      this.runtimeDirty = false;
    } catch (error) {
      this.backendSettings = { ...DEFAULT_BACKEND_SETTINGS };
      this.runtimeDirty = false;
      new Notice(`ProjectOS runtime settings unavailable: ${String(error)}`);
    }
  }

  applyPreset(settings: Partial<BackendSettings>): void {
    this.backendSettings = mergeBackendSettings({ ...this.backendSettings, ...settings });
    this.runtimeDirty = true;
  }

  markRuntimeDirty(): void {
    this.runtimeDirty = true;
  }

  async saveBackendSettings(): Promise<void> {
    this.status = "Saving runtime settings...";
    try {
      this.backendSettings = await this.client.setBackendSettings(this.backendSettings);
      this.runtimeDirty = false;
      this.status = "Runtime settings saved.";
      new Notice("ProjectOS runtime settings saved.");
    } catch (error) {
      this.fail("Runtime settings failed.", error);
    }
  }

  watch(taskId: string, onCompleted?: () => void, onUpdate?: (data: TaskUpdate) => void): void {
    this.client.watchTask(
      taskId,
      (data) => {
        this.task = data;
        this.status = `${data.progress ?? 0}% ${data.message ?? ""}`;
        onUpdate?.(data);
      },
      (status) => {
        if (status === "completed") onCompleted?.();
      },
      () => {
        this.status = "Task stream disconnected.";
      },
    );
  }

  async runAnalysis(): Promise<void> {
    const projectId = this.requireProjectId();
    if (!projectId) return;
    this.status = "Starting analysis...";
    try {
      const task = await this.client.startAnalysis(projectId);
      this.watch(task.task_id, () => this.loadAnalysis());
    } catch (error) {
      this.fail("Analysis failed.", error);
    }
  }

  async loadAnalysis(): Promise<void> {
    const projectId = this.requireProjectId();
    if (!projectId) return;
    this.status = "Loading analysis...";
    try {
      this.analysis = await this.client.getAnalysis(projectId);
      this.status = "Analysis loaded.";
    } catch (error) {
      this.fail("Analysis unavailable.", error);
    }
  }

  async runSimulation(query: string): Promise<void> {
    const projectId = this.requireProjectId();
    if (!projectId) return;
    this.status = "Starting simulation...";
    this.simulation = null;
    this.simulationLive = "Preparing local LLM persona simulation...";
    try {
      const task = await this.client.startSimulation(projectId, query);
      this.watch(
        task.task_id,
        () => this.loadSimulation(),
        (data) => {
          this.simulationLive = String(data.message ?? "Simulation running...");
        },
      );
    } catch (error) {
      this.simulationLive = "Simulation failed.";
      this.fail("Simulation failed.", error);
    }
  }

  async loadSimulation(): Promise<void> {
    const projectId = this.requireProjectId();
    if (!projectId) return;
    this.status = "Loading simulation...";
    try {
      this.simulation = await this.client.getSimulation(projectId);
      this.simulationLive = "Simulation result loaded.";
      this.status = "Simulation loaded.";
    } catch (error) {
      this.fail("Simulation unavailable.", error);
    }
  }

  async ask(question: string): Promise<void> {
    const projectId = this.requireProjectId();
    if (!projectId || !question.trim()) return;
    this.answer = "";
    this.status = "Asking...";
    try {
      await this.client.streamChat(projectId, question, (token) => {
        this.answer += token;
      });
      this.status = "Done.";
    } catch (error) {
      this.fail("Query failed.", error);
    }
  }
}
```

- [ ] **Step 2: Build to typecheck**

Run: `npm run build`
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add src/obsidian-plugin/src/store/appStore.svelte.ts
git commit -m "feat: add runes app store for plugin state and actions"
```

---

## Task 8: UI primitives

**Files:**
- Create: `src/obsidian-plugin/src/ui/Card.svelte`
- Create: `src/obsidian-plugin/src/ui/Button.svelte`
- Create: `src/obsidian-plugin/src/ui/StatusPill.svelte`
- Create: `src/obsidian-plugin/src/ui/ProgressBar.svelte`
- Create: `src/obsidian-plugin/src/ui/Disclosure.svelte`
- Create: `src/obsidian-plugin/src/ui/Tabs.svelte`

- [ ] **Step 1: Card.svelte**

```svelte
<script lang="ts">
  import type { Snippet } from "svelte";
  let { title, subtitle, header, children }: {
    title: string;
    subtitle?: string;
    header?: Snippet;
    children: Snippet;
  } = $props();
</script>

<section class="pos-card">
  <div class="pos-card-head">
    <div>
      <h3>{title}</h3>
      {#if subtitle}<p class="pos-muted">{subtitle}</p>{/if}
    </div>
    {#if header}<div class="pos-card-head-extra">{@render header()}</div>{/if}
  </div>
  <div class="pos-card-body">{@render children()}</div>
</section>
```

- [ ] **Step 2: Button.svelte**

```svelte
<script lang="ts">
  import type { Snippet } from "svelte";
  let { variant = "default", disabled = false, onclick, children }: {
    variant?: "default" | "primary";
    disabled?: boolean;
    onclick?: () => void;
    children: Snippet;
  } = $props();
</script>

<button class="pos-btn pos-btn-{variant}" {disabled} {onclick}>{@render children()}</button>
```

- [ ] **Step 3: StatusPill.svelte**

```svelte
<script lang="ts">
  let { state = "idle", label }: {
    state?: "idle" | "running" | "done" | "error";
    label: string;
  } = $props();
</script>

<span class="pos-pill pos-pill-{state}">{label}</span>
```

- [ ] **Step 4: ProgressBar.svelte**

```svelte
<script lang="ts">
  let { progress = 0, active = false }: { progress?: number; active?: boolean } = $props();
</script>

{#if active}
  <div class="pos-progress">
    <div class="pos-progress-fill" style:width={`${Math.max(0, Math.min(100, progress))}%`}></div>
  </div>
{/if}
```

- [ ] **Step 5: Disclosure.svelte**

```svelte
<script lang="ts">
  import { slide } from "svelte/transition";
  import type { Snippet } from "svelte";
  let { label, open = false, children }: { label: string; open?: boolean; children: Snippet } = $props();
  let expanded = $state(open);
</script>

<div class="pos-disclosure">
  <button class="pos-disclosure-summary" onclick={() => (expanded = !expanded)}>
    <span class="pos-disclosure-icon" class:open={expanded}>▶</span>{label}
  </button>
  {#if expanded}
    <div class="pos-disclosure-body" transition:slide={{ duration: 150 }}>{@render children()}</div>
  {/if}
</div>
```

- [ ] **Step 6: Tabs.svelte**

```svelte
<script lang="ts">
  import { fade } from "svelte/transition";
  import type { Snippet } from "svelte";
  let { tabs, children }: { tabs: string[]; children: Snippet<[string]> } = $props();
  let active = $state(tabs[0]);
  $effect(() => {
    if (!tabs.includes(active)) active = tabs[0];
  });
</script>

<div class="pos-tabs">
  {#each tabs as tab}
    <button class="pos-tab" class:is-active={tab === active} onclick={() => (active = tab)}>{tab}</button>
  {/each}
</div>
{#key active}
  <div class="pos-tab-panel" transition:fade={{ duration: 120 }}>{@render children(active)}</div>
{/key}
```

- [ ] **Step 7: Build to verify components compile**

Run: `npm run build`
Expected: build succeeds (components compile even if unused).

- [ ] **Step 8: Commit**

```bash
git add src/obsidian-plugin/src/ui
git commit -m "feat: add svelte ui primitives for plugin panel"
```

---

## Task 9: Project, Sync, Collect sections

**Files:**
- Create: `src/obsidian-plugin/src/sections/ProjectSection.svelte`
- Create: `src/obsidian-plugin/src/sections/SyncSection.svelte`
- Create: `src/obsidian-plugin/src/sections/CollectSection.svelte`

- [ ] **Step 1: ProjectSection.svelte**

```svelte
<script lang="ts">
  import Card from "../ui/Card.svelte";
  import Button from "../ui/Button.svelte";
  import Disclosure from "../ui/Disclosure.svelte";
  import type { AppStore } from "../store/appStore.svelte";

  let { store }: { store: AppStore } = $props();
  let newName = $state(store.plugin.settings.projectName);
</script>

<Card title="Project" subtitle="Select a backend project.">
  <select
    class="pos-input"
    value={store.projectId}
    onchange={(e) => store.selectProject((e.currentTarget as HTMLSelectElement).value)}
  >
    <option value="">Select project</option>
    {#each store.projects as project}
      <option value={project.project_id}>{project.name} ({project.project_id})</option>
    {/each}
  </select>

  <Disclosure label="Project management">
    <input class="pos-input" type="text" placeholder="New project name" bind:value={newName} />
    <div class="pos-actions">
      <Button onclick={() => store.refreshProjects()}>Refresh</Button>
      <Button variant="primary" onclick={() => store.createProject(newName)}>Create project</Button>
    </div>
    <div class="pos-project-list">
      {#if !store.projects.length}
        <div class="pos-empty">No backend projects found.</div>
      {/if}
      {#each store.projects as project}
        <button
          class="pos-project-item"
          class:is-selected={project.project_id === store.projectId}
          onclick={() => store.selectProject(project.project_id)}
        >
          <div class="pos-project-main">
            <strong>{project.name}</strong>
            {#if project.description}<span>{project.description}</span>{/if}
          </div>
          <div class="pos-project-meta">
            <span>{project.status ?? "unknown"}</span>
            <code>{project.project_id}</code>
          </div>
        </button>
      {/each}
    </div>
  </Disclosure>
</Card>
```

- [ ] **Step 2: SyncSection.svelte**

```svelte
<script lang="ts">
  import { Notice } from "obsidian";
  import Card from "../ui/Card.svelte";
  import Button from "../ui/Button.svelte";
  import { writePayloadToVault } from "../lib/graphColors";
  import type { App } from "obsidian";
  import type { AppStore } from "../store/appStore.svelte";

  let { store, app }: { store: AppStore; app: App } = $props();

  async function sync(): Promise<void> {
    const projectId = store.requireProjectId();
    if (!projectId) return;
    store.status = "Syncing...";
    try {
      const payload = await store.client.exportVault(projectId);
      const count = await writePayloadToVault(app, payload, store.targetFolder());
      store.status = `Synced ${count} notes.`;
      new Notice(`ProjectOS synced ${count} notes.`);
    } catch (error) {
      store.status = "Sync failed.";
      new Notice(`ProjectOS sync failed: ${String(error)}`);
    }
  }
</script>

<Card title="Sync" subtitle="Pull generated notes into this vault.">
  <Button onclick={sync}>Pull from backend</Button>
</Card>
```

- [ ] **Step 3: CollectSection.svelte**

```svelte
<script lang="ts">
  import { Notice } from "obsidian";
  import Card from "../ui/Card.svelte";
  import Button from "../ui/Button.svelte";
  import type { AppStore } from "../store/appStore.svelte";

  let { store }: { store: AppStore } = $props();
  let files = $state<FileList | null>(null);

  async function uploadAndBuild(): Promise<void> {
    const projectId = store.requireProjectId();
    if (!projectId || !files || files.length === 0) return;
    store.status = "Uploading...";
    try {
      await store.client.uploadFiles(projectId, files);
      const task = await store.client.startGraphBuild(projectId);
      store.status = "Build started.";
      store.watch(task.task_id);
    } catch (error) {
      store.status = "Upload/build failed.";
      new Notice(`ProjectOS build failed: ${String(error)}`);
    }
  }
</script>

<Card title="Collect" subtitle="Upload files and start graph build.">
  <input
    class="pos-file"
    type="file"
    multiple
    onchange={(e) => (files = (e.currentTarget as HTMLInputElement).files)}
  />
  <Button onclick={uploadAndBuild}>Upload and build</Button>
</Card>
```

- [ ] **Step 4: Build**

Run: `npm run build`
Expected: build succeeds.

- [ ] **Step 5: Commit**

```bash
git add src/obsidian-plugin/src/sections/ProjectSection.svelte src/obsidian-plugin/src/sections/SyncSection.svelte src/obsidian-plugin/src/sections/CollectSection.svelte
git commit -m "feat: add project, sync, collect svelte sections"
```

---

## Task 10: Runtime, Analysis sections

**Files:**
- Create: `src/obsidian-plugin/src/sections/RuntimeSection.svelte`
- Create: `src/obsidian-plugin/src/sections/AnalysisSection.svelte`

- [ ] **Step 1: RuntimeSection.svelte**

```svelte
<script lang="ts">
  import Card from "../ui/Card.svelte";
  import Button from "../ui/Button.svelte";
  import StatusPill from "../ui/StatusPill.svelte";
  import Disclosure from "../ui/Disclosure.svelte";
  import { RUNTIME_PRESETS, matchRuntimePreset, parsePositiveInt, DEFAULT_BACKEND_SETTINGS } from "../lib/runtime";
  import type { AppStore } from "../store/appStore.svelte";

  let { store }: { store: AppStore } = $props();

  const presetId = $derived(matchRuntimePreset(store.backendSettings));
  const presetTitle = $derived(
    presetId ? RUNTIME_PRESETS.find((p) => p.id === presetId)?.title : "Custom",
  );
  const note = $derived(
    store.backendSettings.graph_build_mode === "claude_task"
      ? "Claude Task mode runs without local LLM extraction and uses isolated task instructions."
      : store.backendSettings.graph_extraction_backend === "claude_code"
        ? "Chunk mode will call Claude Code for extraction batches. Increase chunk size to reduce calls."
        : "Chunk mode uses the local OpenAI-compatible endpoint for extraction.",
  );

  function setField<K extends keyof typeof store.backendSettings>(key: K, value: (typeof store.backendSettings)[K]): void {
    store.backendSettings = { ...store.backendSettings, [key]: value };
    store.markRuntimeDirty();
  }
</script>

<Card title="Runtime" subtitle="Current graph build backend.">
  {#snippet header()}
    <StatusPill state={store.runtimeDirty ? "running" : "done"} label={store.runtimeDirty ? "Unsaved" : "Saved"} />
  {/snippet}

  <div class="pos-runtime-state">
    <span class="pos-runtime-label">{presetTitle} / {store.backendSettings.graph_build_mode}</span>
  </div>

  <Disclosure label="Runtime settings">
    <div class="pos-presets">
      {#each RUNTIME_PRESETS as preset}
        <button
          class="pos-preset"
          class:is-active={preset.id === presetId}
          onclick={() => store.applyPreset(preset.settings)}
        >
          <strong>{preset.title}</strong>
          <span>{preset.description}</span>
        </button>
      {/each}
    </div>

    <label class="pos-field-label">LLM backend</label>
    <select class="pos-input" value={store.backendSettings.llm_backend} onchange={(e) => setField("llm_backend", (e.currentTarget as HTMLSelectElement).value)}>
      <option value="local">Local LLM</option>
      <option value="claude_code">Claude Code</option>
    </select>

    <label class="pos-field-label">Graph build mode</label>
    <select class="pos-input" value={store.backendSettings.graph_build_mode} onchange={(e) => setField("graph_build_mode", (e.currentTarget as HTMLSelectElement).value)}>
      <option value="chunk">Chunk extraction</option>
      <option value="claude_task">Claude task mode</option>
    </select>

    <label class="pos-field-label">Chunk extraction backend</label>
    <select class="pos-input" value={store.backendSettings.graph_extraction_backend} onchange={(e) => setField("graph_extraction_backend", (e.currentTarget as HTMLSelectElement).value)}>
      <option value="local">Local LLM</option>
      <option value="claude_code">Claude Code</option>
    </select>

    <div class="pos-field-grid">
      <div>
        <label class="pos-field-label">Claude Code model</label>
        <input class="pos-input" type="text" placeholder="claude-haiku-4-5" value={store.backendSettings.claude_code_model} oninput={(e) => setField("claude_code_model", (e.currentTarget as HTMLInputElement).value.trim())} />
      </div>
      <div>
        <label class="pos-field-label">Chunk size</label>
        <input class="pos-input" type="number" placeholder="500" value={store.backendSettings.chunk_size} oninput={(e) => setField("chunk_size", parsePositiveInt((e.currentTarget as HTMLInputElement).value, DEFAULT_BACKEND_SETTINGS.chunk_size))} />
      </div>
      <div>
        <label class="pos-field-label">Chunk overlap</label>
        <input class="pos-input" type="number" placeholder="50" value={store.backendSettings.chunk_overlap} oninput={(e) => setField("chunk_overlap", parsePositiveInt((e.currentTarget as HTMLInputElement).value, DEFAULT_BACKEND_SETTINGS.chunk_overlap))} />
      </div>
    </div>

    <p class="pos-muted pos-runtime-note">{note}</p>

    <div class="pos-actions">
      <Button onclick={() => store.loadBackendSettings()}>Reload</Button>
      <Button variant="primary" onclick={() => store.saveBackendSettings()}>Save runtime</Button>
    </div>
  </Disclosure>
</Card>
```

- [ ] **Step 2: AnalysisSection.svelte**

```svelte
<script lang="ts">
  import Card from "../ui/Card.svelte";
  import Button from "../ui/Button.svelte";
  import type { AppStore } from "../store/appStore.svelte";

  let { store }: { store: AppStore } = $props();
  const a = $derived(store.analysis);
</script>

<Card title="Analysis" subtitle="Review uploaded documents and improvement points.">
  <div class="pos-actions">
    <Button onclick={() => store.runAnalysis()}>Run analysis</Button>
    <Button onclick={() => store.loadAnalysis()}>Load result</Button>
  </div>

  {#if a}
    <div class="pos-result">
      <div class="pos-summary">
        <div class="pos-summary-title">Summary</div>
        <p>{a.summary || "No summary."}</p>
        {#if a.generated_at}<span class="pos-meta">{new Date(a.generated_at).toLocaleString()}</span>{/if}
      </div>
      <div class="pos-summary-title">Improvement points</div>
      {#if !(a.issues?.length)}
        <p class="pos-muted">No issues found.</p>
      {/if}
      {#each a.issues ?? [] as issue}
        <div class="pos-issue">
          <span class="pos-severity pos-severity-{issue.severity ?? 'medium'}">{issue.severity ?? "medium"}</span>
          <strong>{issue.category ?? "Issue"}</strong>
          <p>{issue.description ?? ""}</p>
          <div class="pos-suggestion">{issue.suggestion ?? ""}</div>
        </div>
      {/each}
      {#if a.improved_draft}
        <div class="pos-summary-title">Improved draft</div>
        <pre class="pos-draft">{a.improved_draft}</pre>
      {/if}
    </div>
  {/if}
</Card>
```

- [ ] **Step 3: Build**

Run: `npm run build`
Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add src/obsidian-plugin/src/sections/RuntimeSection.svelte src/obsidian-plugin/src/sections/AnalysisSection.svelte
git commit -m "feat: add runtime and analysis svelte sections"
```

---

## Task 11: Simulation and Query sections

**Files:**
- Create: `src/obsidian-plugin/src/sections/SimulationSection.svelte`
- Create: `src/obsidian-plugin/src/sections/QuerySection.svelte`

- [ ] **Step 1: SimulationSection.svelte**

```svelte
<script lang="ts">
  import { fly } from "svelte/transition";
  import Card from "../ui/Card.svelte";
  import Button from "../ui/Button.svelte";
  import Tabs from "../ui/Tabs.svelte";
  import StatusPill from "../ui/StatusPill.svelte";
  import type { AppStore } from "../store/appStore.svelte";

  let { store }: { store: AppStore } = $props();
  let query = $state("");
  const r = $derived(store.simulation);
  const changes = $derived(r?.applied_graph_changes ?? {});
  const recommendations = $derived(r?.report?.recommendations ?? r?.cv_improvements?.bullets ?? []);
</script>

<Card title="Simulation" subtitle="Persona simulation and reports.">
  <textarea class="pos-textarea" rows="4" placeholder="Query, CV goal, or report request" bind:value={query}></textarea>
  <div class="pos-actions">
    <Button variant="primary" onclick={() => store.runSimulation(query)}>Run simulation</Button>
    <Button onclick={() => store.loadSimulation()}>Load result</Button>
  </div>
  {#if store.simulationLive}<p class="pos-muted pos-runtime-note">{store.simulationLive}</p>{/if}

  {#if r}
    <Tabs tabs={["Report", "Agents", "Timeline", "CV"]}>
      {#snippet children(tab)}
        {#if tab === "Report"}
          <div class="pos-summary">
            <div class="pos-summary-title">{r.report?.title || "Simulation report"}</div>
            <p>{r.report?.answer || r.environment?.objective || "No report."}</p>
            <span class="pos-meta">Graph changes: +{changes.nodes_added ?? 0} nodes, +{changes.edges_added ?? 0} edges</span>
          </div>
          {#if recommendations.length}
            <div class="pos-summary-title">Recommendations</div>
            {#each recommendations as rec}<div class="pos-suggestion">{rec}</div>{/each}
          {/if}
        {:else if tab === "Agents"}
          {#if !(r.personas?.length)}<p class="pos-muted">No persona agents.</p>{/if}
          {#each r.personas ?? [] as persona, i}
            <div class="pos-issue" in:fly={{ y: 8, delay: i * 40, duration: 200 }}>
              <strong>{persona.name || "Agent"} ({persona.agent_id || ""})</strong>
              <p>{persona.role || ""}</p>
              {#each [...(persona.goals ?? []), ...(persona.knowledge ?? [])].slice(0, 5) as goal}
                <div class="pos-suggestion">{goal}</div>
              {/each}
            </div>
          {/each}
        {:else if tab === "Timeline"}
          {#if !(r.timeline?.length)}<p class="pos-muted">No agent timeline.</p>{/if}
          {#each r.timeline ?? [] as event, i}
            <div class="pos-timeline-item" in:fly={{ y: 8, delay: i * 30, duration: 200 }}>
              <StatusPill state="running" label={`Round ${event.round ?? "?"} · ${event.agent_id ?? "agent"}`} />
              <p>{event.observation || ""}</p>
              <div class="pos-suggestion">{event.proposal || ""}</div>
            </div>
          {/each}
        {:else if tab === "CV"}
          {#if r.cv_improvements?.improved_draft}
            <div class="pos-summary-title">Improved draft</div>
            <pre class="pos-draft">{r.cv_improvements.improved_draft}</pre>
          {:else}
            <p class="pos-muted">{r.cv_improvements?.summary || "No CV draft."}</p>
          {/if}
        {/if}
      {/snippet}
    </Tabs>
  {/if}
</Card>
```

- [ ] **Step 2: QuerySection.svelte**

```svelte
<script lang="ts">
  import Card from "../ui/Card.svelte";
  import Button from "../ui/Button.svelte";
  import type { AppStore } from "../store/appStore.svelte";

  let { store }: { store: AppStore } = $props();
  let question = $state("");
</script>

<Card title="Query" subtitle="Ask through ProjectOS QueryAgent.">
  <textarea class="pos-textarea" rows="4" bind:value={question}></textarea>
  <Button onclick={() => store.ask(question)}>Ask</Button>
  {#if store.answer}<div class="pos-answer">{store.answer}</div>{/if}
</Card>
```

- [ ] **Step 3: Build**

Run: `npm run build`
Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add src/obsidian-plugin/src/sections/SimulationSection.svelte src/obsidian-plugin/src/sections/QuerySection.svelte
git commit -m "feat: add simulation and query svelte sections"
```

---

## Task 12: App.svelte shell and main.ts rewrite

**Files:**
- Modify: `src/obsidian-plugin/src/App.svelte` (replace stub)
- Modify: `src/obsidian-plugin/src/main.ts` (replace stub with full plugin)

- [ ] **Step 1: App.svelte**

Replace `src/obsidian-plugin/src/App.svelte`:
```svelte
<script lang="ts">
  import type { App } from "obsidian";
  import type { AppStore } from "./store/appStore.svelte";
  import ProgressBar from "./ui/ProgressBar.svelte";
  import ProjectSection from "./sections/ProjectSection.svelte";
  import RuntimeSection from "./sections/RuntimeSection.svelte";
  import SyncSection from "./sections/SyncSection.svelte";
  import CollectSection from "./sections/CollectSection.svelte";
  import AnalysisSection from "./sections/AnalysisSection.svelte";
  import SimulationSection from "./sections/SimulationSection.svelte";
  import QuerySection from "./sections/QuerySection.svelte";

  let { store, app }: { store: AppStore; app: App } = $props();
  const taskActive = $derived(
    store.task != null && store.task.status !== "completed" && store.task.status !== "failed",
  );
</script>

<div class="pos-panel">
  <header class="pos-header">
    <h2>ProjectOS</h2>
    <div class="pos-status">{store.status}</div>
    <ProgressBar progress={store.task?.progress ?? 0} active={taskActive} />
  </header>

  <ProjectSection {store} />
  <RuntimeSection {store} />
  <SyncSection {store} {app} />
  <CollectSection {store} />
  <AnalysisSection {store} />
  <SimulationSection {store} />
  <QuerySection {store} />
</div>
```

- [ ] **Step 2: main.ts — full plugin with Svelte mount + native settings tab**

Replace `src/obsidian-plugin/src/main.ts`:
```ts
import {
  App,
  DropdownComponent,
  ItemView,
  Notice,
  Plugin,
  PluginSettingTab,
  Setting,
  TextComponent,
  WorkspaceLeaf,
} from "obsidian";
import { mount, unmount } from "svelte";

import App_ from "./App.svelte";
import { ApiClient } from "./api/client";
import { AppStore } from "./store/appStore.svelte";
import {
  BackendSettings,
  DEFAULT_BACKEND_SETTINGS,
  RUNTIME_PRESETS,
  mergeBackendSettings,
  parsePositiveInt,
} from "./lib/runtime";

const VIEW_TYPE_PROJECTOS = "projectos-vault-sync-view";

interface ProjectOSSettings {
  baseUrl: string;
  projectId: string;
  projectName: string;
  targetFolder: string;
}

const DEFAULT_SETTINGS: ProjectOSSettings = {
  baseUrl: "http://localhost:8002",
  projectId: "",
  projectName: "",
  targetFolder: "",
};

export default class ProjectOSPlugin extends Plugin {
  settings: ProjectOSSettings = DEFAULT_SETTINGS;
  client = new ApiClient(() => this.settings.baseUrl);

  async onload(): Promise<void> {
    await this.loadSettings();
    this.registerView(VIEW_TYPE_PROJECTOS, (leaf) => new ProjectOSView(leaf, this));
    this.addRibbonIcon("network", "ProjectOS", () => this.activateView());
    this.addCommand({
      id: "open-projectos-panel",
      name: "Open ProjectOS panel",
      callback: () => this.activateView(),
    });
    this.addSettingTab(new ProjectOSSettingTab(this.app, this));
  }

  async loadSettings(): Promise<void> {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
  }

  async saveSettings(): Promise<void> {
    await this.saveData(this.settings);
  }

  async activateView(): Promise<void> {
    const { workspace } = this.app;
    let leaf: WorkspaceLeaf | null = workspace.getLeavesOfType(VIEW_TYPE_PROJECTOS)[0] ?? null;
    if (!leaf) {
      leaf = workspace.getRightLeaf(false);
      await leaf?.setViewState({ type: VIEW_TYPE_PROJECTOS, active: true });
    }
    if (leaf) workspace.revealLeaf(leaf);
  }

  async getBackendSettings(): Promise<BackendSettings> {
    return this.client.getBackendSettings();
  }

  async setBackendSettings(settings: BackendSettings): Promise<BackendSettings> {
    return this.client.setBackendSettings(settings);
  }
}

class ProjectOSView extends ItemView {
  plugin: ProjectOSPlugin;
  private component: ReturnType<typeof mount> | null = null;

  constructor(leaf: WorkspaceLeaf, plugin: ProjectOSPlugin) {
    super(leaf);
    this.plugin = plugin;
  }

  getViewType(): string {
    return VIEW_TYPE_PROJECTOS;
  }

  getDisplayText(): string {
    return "ProjectOS";
  }

  async onOpen(): Promise<void> {
    const root = this.containerEl.children[1] as HTMLElement;
    root.empty();
    const store = new AppStore(this.plugin.client, this.plugin);
    this.component = mount(App_, { target: root, props: { store, app: this.app } });
    await store.loadBackendSettings();
    await store.refreshProjects();
  }

  async onClose(): Promise<void> {
    if (this.component) {
      unmount(this.component);
      this.component = null;
    }
  }
}

class ProjectOSSettingTab extends PluginSettingTab {
  plugin: ProjectOSPlugin;

  constructor(app: App, plugin: ProjectOSPlugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display(): void {
    const { containerEl } = this;
    containerEl.empty();

    new Setting(containerEl).setName("Backend base URL").addText((text) =>
      text
        .setPlaceholder("http://localhost:8002")
        .setValue(this.plugin.settings.baseUrl)
        .onChange(async (value) => {
          this.plugin.settings.baseUrl = value.trim() || DEFAULT_SETTINGS.baseUrl;
          await this.plugin.saveSettings();
        }),
    );

    new Setting(containerEl)
      .setName("Project ID")
      .setDesc("Auto-filled when a project is created or selected in the ProjectOS panel.")
      .addText((text) =>
        text
          .setPlaceholder("Created from the ProjectOS panel")
          .setValue(this.plugin.settings.projectId)
          .onChange(async (value) => {
            this.plugin.settings.projectId = value.trim();
            await this.plugin.saveSettings();
          }),
      );

    new Setting(containerEl).setName("Target folder").addText((text) =>
      text
        .setPlaceholder("ProjectOS")
        .setValue(this.plugin.settings.targetFolder)
        .onChange(async (value) => {
          this.plugin.settings.targetFolder = value.trim();
          await this.plugin.saveSettings();
        }),
    );

    this.renderRuntimeSettings(containerEl);
  }

  renderRuntimeSettings(containerEl: HTMLElement): void {
    const section = containerEl.createDiv({ cls: "projectos-settings-runtime" });
    section.createEl("h3", { text: "Backend runtime" });
    section.createEl("p", {
      cls: "projectos-muted",
      text: "These values are stored in the ProjectOS backend and affect the next graph build.",
    });

    let llmBackend: DropdownComponent;
    let graphMode: DropdownComponent;
    let graphBackend: DropdownComponent;
    let claudeModel: TextComponent;
    let chunkSize: TextComponent;
    let chunkOverlap: TextComponent;

    const setControls = (settings: Partial<BackendSettings>): void => {
      const merged = mergeBackendSettings(settings);
      llmBackend.setValue(merged.llm_backend);
      graphMode.setValue(merged.graph_build_mode);
      graphBackend.setValue(merged.graph_extraction_backend);
      claudeModel.setValue(merged.claude_code_model);
      chunkSize.setValue(String(merged.chunk_size));
      chunkOverlap.setValue(String(merged.chunk_overlap));
    };

    const readControls = (): BackendSettings => ({
      llm_backend: llmBackend.getValue(),
      graph_build_mode: graphMode.getValue(),
      graph_extraction_backend: graphBackend.getValue(),
      claude_code_model: claudeModel.getValue().trim(),
      chunk_size: parsePositiveInt(chunkSize.getValue(), DEFAULT_BACKEND_SETTINGS.chunk_size),
      chunk_overlap: parsePositiveInt(chunkOverlap.getValue(), DEFAULT_BACKEND_SETTINGS.chunk_overlap),
    });

    new Setting(section)
      .setName("Preset")
      .setDesc("Quickly switch the graph build behavior.")
      .addDropdown((dropdown) => {
        for (const preset of RUNTIME_PRESETS) dropdown.addOption(preset.id, preset.title);
        dropdown.onChange((value) => {
          const preset = RUNTIME_PRESETS.find((item) => item.id === value);
          if (preset) setControls(preset.settings);
        });
      });

    new Setting(section).setName("LLM backend").addDropdown((dropdown) => {
      llmBackend = dropdown.addOption("local", "Local LLM").addOption("claude_code", "Claude Code");
    });

    new Setting(section).setName("Graph build mode").addDropdown((dropdown) => {
      graphMode = dropdown.addOption("chunk", "Chunk extraction").addOption("claude_task", "Claude task mode");
    });

    new Setting(section).setName("Chunk extraction backend").addDropdown((dropdown) => {
      graphBackend = dropdown.addOption("local", "Local LLM").addOption("claude_code", "Claude Code");
    });

    new Setting(section).setName("Claude Code model").addText((text) => {
      claudeModel = text.setPlaceholder("claude-haiku-4-5");
    });

    new Setting(section).setName("Chunk size").addText((text) => {
      chunkSize = text.setPlaceholder("1800");
    });

    new Setting(section).setName("Chunk overlap").addText((text) => {
      chunkOverlap = text.setPlaceholder("150");
    });

    new Setting(section)
      .addButton((button) =>
        button.setButtonText("Reload").onClick(async () => {
          try {
            setControls(await this.plugin.getBackendSettings());
            new Notice("ProjectOS runtime settings loaded.");
          } catch (error) {
            setControls(DEFAULT_BACKEND_SETTINGS);
            new Notice(`ProjectOS runtime settings unavailable: ${String(error)}`);
          }
        }),
      )
      .addButton((button) =>
        button
          .setButtonText("Save runtime")
          .setCta()
          .onClick(async () => {
            try {
              setControls(await this.plugin.setBackendSettings(readControls()));
              new Notice("ProjectOS runtime settings saved.");
            } catch (error) {
              new Notice(`ProjectOS runtime settings failed: ${String(error)}`);
            }
          }),
      );

    setControls(DEFAULT_BACKEND_SETTINGS);
    void this.plugin
      .getBackendSettings()
      .then(setControls)
      .catch(() => setControls(DEFAULT_BACKEND_SETTINGS));
  }
}
```

- [ ] **Step 3: Build**

Run: `npm run build`
Expected: build succeeds, `main.js` regenerated.

- [ ] **Step 4: Run tests**

Run: `npm test`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/obsidian-plugin/src/App.svelte src/obsidian-plugin/src/main.ts
git commit -m "feat: assemble svelte panel app and rewrite plugin entry"
```

---

## Task 13: Rewrite styles.css (theme-adaptive + animations)

**Files:**
- Modify: `src/obsidian-plugin/styles.css`

- [ ] **Step 1: Replace styles.css**

Replace the whole `src/obsidian-plugin/styles.css` with:
```css
/* ProjectOS panel — theme-adaptive */
.pos-panel,
.pos-panel * {
  box-sizing: border-box;
}

.pos-panel {
  padding: 12px;
  color: var(--text-normal);
}

.pos-header {
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--background-primary);
  padding-bottom: 8px;
  margin-bottom: 8px;
  border-bottom: 1px solid var(--background-modifier-border);
}

.pos-header h2 {
  margin: 0;
  font-size: 18px;
}

.pos-status {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 2px;
  overflow-wrap: anywhere;
}

.pos-progress {
  height: 3px;
  margin-top: 6px;
  background: var(--background-modifier-border);
  border-radius: 2px;
  overflow: hidden;
}

.pos-progress-fill {
  height: 100%;
  background: var(--interactive-accent);
  transition: width 0.3s ease;
}

.pos-card {
  background: var(--background-secondary);
  border: 1px solid var(--background-modifier-border);
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 12px;
  overflow: hidden;
  animation: pos-fade-in 0.25s ease both;
}

@keyframes pos-fade-in {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: none; }
}

.pos-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}

.pos-card-head h3 {
  margin: 0;
  font-size: 14px;
}

.pos-muted {
  color: var(--text-muted);
  font-size: 12px;
  margin: 2px 0 0;
}

.pos-input,
.pos-textarea,
.pos-file {
  width: 100%;
  margin-bottom: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  border: 1px solid var(--background-modifier-border);
  background: var(--background-primary);
  color: var(--text-normal);
  font-size: 13px;
}

.pos-textarea {
  resize: vertical;
  font-family: inherit;
}

.pos-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 4px 0 8px;
}

.pos-btn {
  padding: 6px 12px;
  border-radius: 6px;
  border: 1px solid var(--background-modifier-border);
  background: var(--background-primary);
  color: var(--text-normal);
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s ease, transform 0.05s ease;
}

.pos-btn:hover { background: var(--background-modifier-hover); }
.pos-btn:active { transform: scale(0.98); }
.pos-btn:disabled { opacity: 0.5; cursor: default; }

.pos-btn-primary {
  background: var(--interactive-accent);
  color: var(--text-on-accent);
  border-color: transparent;
}

.pos-btn-primary:hover { background: var(--interactive-accent-hover); }

.pos-pill {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  transition: background 0.2s ease, color 0.2s ease;
}

.pos-pill-idle { background: var(--background-modifier-border); color: var(--text-muted); }
.pos-pill-running { background: var(--interactive-accent); color: var(--text-on-accent); }
.pos-pill-done { background: var(--background-modifier-success, #2a9d8f); color: var(--text-on-accent); }
.pos-pill-error { background: var(--background-modifier-error, #e76f51); color: var(--text-on-accent); }

.pos-disclosure { margin-top: 8px; }

.pos-disclosure-summary {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 6px 0;
  background: none;
  border: none;
  color: var(--text-normal);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  text-align: left;
}

.pos-disclosure-icon { transition: transform 0.15s ease; font-size: 9px; }
.pos-disclosure-icon.open { transform: rotate(90deg); }
.pos-disclosure-body { padding-top: 8px; }

.pos-presets {
  display: grid;
  gap: 8px;
  margin-bottom: 10px;
}

.pos-preset {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
  height: auto;
  text-align: left;
  padding: 8px 10px;
  border-radius: 6px;
  border: 1px solid var(--background-modifier-border);
  background: var(--background-primary);
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
}

.pos-preset:hover { background: var(--background-modifier-hover); }
.pos-preset.is-active { border-color: var(--interactive-accent); }
.pos-preset strong { font-size: 13px; }
.pos-preset span { font-size: 11px; color: var(--text-muted); }

.pos-field-label {
  display: block;
  font-size: 11px;
  color: var(--text-muted);
  margin: 6px 0 2px;
}

.pos-field-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 4px;
}

.pos-runtime-state { margin-bottom: 4px; }
.pos-runtime-label { font-size: 12px; color: var(--text-muted); }
.pos-runtime-note { margin-top: 6px; }

.pos-project-list { display: grid; gap: 6px; margin-top: 8px; }

.pos-project-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  text-align: left;
  padding: 8px;
  border-radius: 6px;
  border: 1px solid var(--background-modifier-border);
  background: var(--background-primary);
  cursor: pointer;
}

.pos-project-item.is-selected { border-color: var(--interactive-accent); }
.pos-project-main strong { font-size: 13px; }
.pos-project-main span { font-size: 11px; color: var(--text-muted); display: block; }
.pos-project-meta { display: flex; gap: 8px; align-items: center; }
.pos-project-meta code { font-size: 10px; color: var(--text-muted); }
.pos-empty { font-size: 12px; color: var(--text-muted); padding: 8px; }

.pos-tabs {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid var(--background-modifier-border);
  margin-bottom: 8px;
}

.pos-tab {
  padding: 6px 10px;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-muted);
  font-size: 13px;
  cursor: pointer;
}

.pos-tab.is-active {
  color: var(--text-normal);
  border-bottom-color: var(--interactive-accent);
}

.pos-summary-title { font-size: 12px; font-weight: 600; margin: 8px 0 4px; }
.pos-summary p { margin: 0; font-size: 13px; }
.pos-meta { font-size: 11px; color: var(--text-muted); }

.pos-issue,
.pos-timeline-item {
  border: 1px solid var(--background-modifier-border);
  border-radius: 6px;
  padding: 8px;
  margin-bottom: 8px;
}

.pos-issue p,
.pos-timeline-item p { margin: 4px 0; font-size: 13px; }

.pos-suggestion {
  font-size: 12px;
  color: var(--text-muted);
  padding: 4px 0 0;
}

.pos-severity {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 10px;
  margin-right: 6px;
  background: var(--background-modifier-border);
}

.pos-severity-high { background: var(--background-modifier-error, #e76f51); color: #fff; }
.pos-severity-low { background: var(--background-modifier-success, #2a9d8f); color: #fff; }

.pos-draft,
.pos-answer {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 13px;
  background: var(--background-primary);
  border: 1px solid var(--background-modifier-border);
  border-radius: 6px;
  padding: 8px;
  margin-top: 6px;
}

.projectos-settings-runtime { margin-top: 16px; }
.projectos-muted { color: var(--text-muted); font-size: 12px; }
```

- [ ] **Step 2: Build**

Run: `npm run build`
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add src/obsidian-plugin/styles.css
git commit -m "style: theme-adaptive animated styles for svelte panel"
```

---

## Task 14: Remove old root entry and final verification

**Files:**
- Delete: `src/obsidian-plugin/main.ts` (old monolith)

- [ ] **Step 1: Confirm new entry is the build source**

Run from `src/obsidian-plugin/`: `grep -n "src/main.ts" esbuild.config.mjs`
Expected: shows `entryPoints: ["src/main.ts"]`.

- [ ] **Step 2: Delete the old monolithic file**

Run: `git rm main.ts`
(The root `main.ts` is replaced by `src/main.ts`; `main.js` is the build output and stays.)

- [ ] **Step 3: Full build + tests**

Run: `npm run build && npm test`
Expected: build succeeds; all tests PASS.

- [ ] **Step 4: Confirm no dangling references**

Run: `grep -rn "from \"./vaultSync\"\|from \"../vaultSync\"" src tests`
Expected: no matches (all import from `lib/vaultSync`).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: remove old monolithic plugin entry"
```

- [ ] **Step 6: Update handoff doc**

Append a section to `docs/claude-code-handoff.md` summarizing: Svelte 5 panel rewrite, module structure, settings tab kept native, build/test results, and the still-pending backend simulation fixes (edge type-match fallback, relation normalization, Category target exclusion). Commit:
```bash
git add docs/claude-code-handoff.md
git commit -m "docs: update handoff with svelte plugin redesign"
```

---

## Self-Review Notes

- **Spec coverage:** build wiring (T1-2), module extraction + tests (T3-5), api client/types (T6), store (T7), primitives (T8), all 7 sections (T9-11), App shell + entry + native settings tab (T12), theme-adaptive animated styles (T13), cleanup + verification + handoff (T14). All spec sections covered.
- **Behavior parity:** each section ports the exact handler logic from the reference `main.ts` (project select/create/list, runtime presets/reload/save, sync via `writePayloadToVault`, upload+build+watch, analysis run/load/render, simulation run/load/tabbed render, chat SSE).
- **Type consistency:** `BackendSettings` defined once in `lib/runtime.ts` and imported everywhere; `AppStore` method names (`refreshProjects`, `selectProject`, `createProject`, `loadBackendSettings`, `applyPreset`, `markRuntimeDirty`, `saveBackendSettings`, `watch`, `runAnalysis`, `loadAnalysis`, `runSimulation`, `loadSimulation`, `ask`) referenced consistently across sections and App.
- **No screenshot verification possible** on this server (per CLAUDE.md); final visual check is the user's in macOS Obsidian.
