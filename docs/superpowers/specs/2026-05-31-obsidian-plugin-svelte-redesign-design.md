# Obsidian Plugin Svelte Redesign — Design

Date: 2026-05-31

## Background

The ProjectOS Obsidian plugin side panel is implemented as a single 1180-line
vanilla TypeScript file (`src/obsidian-plugin/main.ts`) that assembles DOM via
`createEl`. It works, but the UI is static and visually plain (see runtime
screenshots), and the monolithic file mixes the plugin entry point, settings
tab, view rendering, API calls, and pure helpers.

This redesign rewrites the **side panel view** with Svelte for a dynamic,
theme-adaptive UI while preserving 100% of existing functionality. The backend
simulation defects found during the same session (edge type-match fallback,
relation normalization, Category target exclusion) are explicitly **out of
scope** here and tracked separately.

## Goals

- Dynamic, animated panel UI that adapts to any Obsidian theme.
- Componentized, maintainable structure replacing the monolithic view.
- Keep all current features behaving identically (no behavior change).
- Keep core logic in testable TS modules.

## Non-Goals

- No backend changes (simulation edge/relation fixes are separate work).
- No change to the settings tab UX (kept native Obsidian `Setting` API).
- No new features beyond what `main.ts` already does.

## Approach

**Panel-only Svelte, native settings tab, logic/UI separation.**

- Only the side panel view (`ProjectOSView`) is rewritten as a Svelte app
  mounted into the view container.
- The settings tab (`ProjectOSSettingTab`) keeps the Obsidian `Setting` API —
  this is the Obsidian convention and renders most naturally across themes.
- API calls, shared state, and formatting move into pure TS modules so they
  stay unit-testable; Svelte components stay thin.

Rejected alternatives: making the settings tab Svelte too (breaks Obsidian
convention, theme dissonance); a single large `App.svelte` (reproduces the
monolith problem).

## Build

- Add `esbuild-svelte` + `svelte-preprocess` to `esbuild.config.mjs`.
- Svelte 5 with runes (`$state`, `$derived`, `$props`).
- Output stays a single `main.js` bundle (Obsidian requirement).
- `styles.css` remains the plugin stylesheet; rewritten to use Obsidian CSS
  variables and section/animation styles.

## Module Structure

Under `src/obsidian-plugin/src/`:

```
main.ts                     Plugin entry: Plugin, ItemView (Svelte mount/unmount), SettingTab
api/types.ts                ProjectSummary, BackendSettings, AnalysisResult, SimulationResult, TaskUpdate
api/client.ts               fetch wrappers: projects, settings, files, graph, analysis, simulation, chat SSE, task stream
lib/vaultSync.ts            existing pure helper (moved from current location)
lib/graphColors.ts          GRAPH_COLOR_GROUPS, ensureGraphColorGroups, writePayloadToVault, clearGenerated
lib/runtime.ts              RUNTIME_PRESETS, mergeBackendSettings, matchRuntimePreset, parsePositiveInt
store/appStore.svelte.ts    shared runes-based state: status, projects, backendSettings, task, analysis, simulation, answer
ui/                         Card, Tabs, StatusPill, ProgressBar, Disclosure, Button (reusable primitives)
sections/                   ProjectSection, RuntimeSection, SyncSection, CollectSection, AnalysisSection, SimulationSection, QuerySection
App.svelte                  header (title + status bar + progress) + 7 sections
```

The `App` and `App.title()` / display-text plumbing in `main.ts` only handles
mounting `App.svelte` into `this.containerEl.children[1]` on `onOpen` and
calling `$destroy`/unmount on `onClose`.

## Data Flow

- Component → `appStore` method → `api/client` fetch → store state update →
  component re-renders reactively.
- Task progress: `client.streamTask(id)` opens an `EventSource` and pushes
  `{progress, message, status}` into `store.task`; the header `ProgressBar` and
  per-section live text both react to it.
- Chat: `client.streamChat(...)` appends tokens to `store.answer` for streaming
  display.

## State (appStore)

```
status: string                       // header status line
task: { progress, message, status } | null
projects: ProjectSummary[]
backendSettings: BackendSettings
runtimeDirty: boolean
analysis: AnalysisResult | null
simulation: SimulationResult | null
answer: string                       // streaming chat output
```

Settings persistence (`projectId`, `projectName`, `baseUrl`, `targetFolder`)
stays on the `Plugin` instance via `loadData`/`saveData`; the store reads/writes
through a thin reference to the plugin.

## Components

**UI primitives**
- `Card` — section container with header (title + subtitle) + slotted body;
  `overflow: hidden`, theme-variable background.
- `Tabs` — tab buttons + animated active panel (fade/slide transition).
- `StatusPill` — colored pill reflecting idle / running / done / error.
- `ProgressBar` — animated bar bound to `store.task.progress`.
- `Disclosure` — `<details>`-style collapsible with expand animation.
- `Button` — variants: default / primary.

**Sections** (1:1 with current functionality)
- `ProjectSection` — select dropdown + collapsible management (name input,
  refresh, create, project list with selected highlight).
- `RuntimeSection` — state pill + collapsible settings (presets, llm backend,
  graph mode, extraction backend, claude model, chunk size/overlap, note text,
  reload/save).
- `SyncSection` — "Pull from backend" → `writePayloadToVault`.
- `CollectSection` — multi-file input + "Upload and build" → watch task.
- `AnalysisSection` — run/load + rendered summary, issues (severity badges),
  improved draft.
- `SimulationSection` — query textarea, run/load, live progress text, tabbed
  result (Report / Agents / Timeline / CV) with persona cards and timeline.
- `QuerySection` — question textarea + "Ask" → SSE streaming answer.

## Visual Design

- Obsidian CSS variables for all colors: `--background-primary`,
  `--background-secondary`, `--background-modifier-border`, `--text-normal`,
  `--text-muted`, `--interactive-accent`.
- Dynamic elements: header progress bar (animated during tasks), tab
  fade/slide transitions, persona-card stagger-in, status-pill color
  transitions, disclosure expand animation.
- Consistent spacing tokens; tidy cards, tabs, badges.

## Error Handling

- Each `api/client` call throws on non-OK; sections catch and set
  `store.status` + show an Obsidian `Notice` (same as today).
- Task stream `onerror` closes the EventSource and reports disconnect.
- Missing project id → `Notice("Create or select a ProjectOS project first.")`.

## Testing

- Pure modules (`lib/runtime.ts`, `lib/graphColors.ts`, `lib/vaultSync.ts`) are
  covered by the existing `tsx --test tests/*.test.ts` runner. The current
  `vaultSync` test must continue to pass after the move.
- `.svelte` components are not unit-tested (logic is extracted to store/modules
  so components stay thin). Verification = type-check + production build success.
- Server environment cannot run Obsidian for screenshots (per CLAUDE.md), so
  final visual confirmation is done by the user in macOS Obsidian.

## Risks

- Svelte 5 + esbuild integration must produce a working single bundle; mitigated
  by a minimal build smoke before porting all sections.
- Behavior regressions during the 1:1 port; mitigated by porting section by
  section against the current `main.ts` as the reference.
