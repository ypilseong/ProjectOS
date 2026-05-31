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
