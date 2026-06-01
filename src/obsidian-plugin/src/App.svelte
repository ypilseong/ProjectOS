<script lang="ts">
  import { fade } from "svelte/transition";
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

  // Each nav item: key, short label, and an inline SVG icon path (24x24 viewBox).
  const NAV = [
    { key: "project", label: "Project", icon: "M3 7h18v13H3zM3 7l2-3h6l2 3" },
    { key: "runtime", label: "Runtime", icon: "M12 8v4l3 2M12 3a9 9 0 100 18 9 9 0 000-18z" },
    { key: "sync", label: "Sync", icon: "M4 12a8 8 0 0114-5l2 2M20 12a8 8 0 01-14 5l-2-2M18 4v5h-5M6 20v-5h5" },
    { key: "collect", label: "Collect", icon: "M12 3v12m0 0l-4-4m4 4l4-4M4 17v2a1 1 0 001 1h14a1 1 0 001-1v-2" },
    { key: "analysis", label: "Analysis", icon: "M4 20V4M4 20h16M8 16V9m4 7V6m4 10v-4" },
    { key: "simulation", label: "Simulate", icon: "M5 12h3l2 6 4-14 2 8h3" },
    { key: "query", label: "Query", icon: "M11 4a7 7 0 105 12l4 4M11 4a7 7 0 017 7" },
  ] as const;

  let active = $state<(typeof NAV)[number]["key"]>("project");
</script>

<div class="pos-panel">
  <header class="pos-header">
    <h2>ProjectOS</h2>
    <div class="pos-status">{store.status}</div>
    <ProgressBar progress={store.task?.progress ?? 0} active={taskActive} />
  </header>

  <nav class="pos-nav" aria-label="Sections">
    {#each NAV as item}
      <button
        type="button"
        class="pos-nav-btn"
        class:is-active={active === item.key}
        aria-current={active === item.key ? "page" : undefined}
        onclick={() => (active = item.key)}
      >
        <svg class="pos-nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
          stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d={item.icon} />
        </svg>
        <span class="pos-nav-label">{item.label}</span>
      </button>
    {/each}
  </nav>

  {#key active}
    <div class="pos-section-panel" in:fade={{ duration: 130 }}>
      {#if active === "project"}<ProjectSection {store} />
      {:else if active === "runtime"}<RuntimeSection {store} />
      {:else if active === "sync"}<SyncSection {store} {app} />
      {:else if active === "collect"}<CollectSection {store} />
      {:else if active === "analysis"}<AnalysisSection {store} />
      {:else if active === "simulation"}<SimulationSection {store} />
      {:else if active === "query"}<QuerySection {store} />
      {/if}
    </div>
  {/key}
</div>
