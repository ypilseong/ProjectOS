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
