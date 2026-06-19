<script lang="ts">
  import type { App } from "obsidian";
  import type { AppStore } from "./store/appStore.svelte";
  import ProjectSection from "./sections/ProjectSection.svelte";
  import SyncSection from "./sections/SyncSection.svelte";

  let { store, app }: { store: AppStore; app: App } = $props();
</script>

<div class="pos-panel">
  <header class="pos-header">
    <h2>ProjectOS</h2>
    <div class="pos-status">{store.status}</div>
  </header>

  <ProjectSection {store} />
  <SyncSection {store} {app} />
</div>
