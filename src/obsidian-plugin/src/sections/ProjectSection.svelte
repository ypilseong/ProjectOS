<script lang="ts">
  import Card from "../ui/Card.svelte";
  import Button from "../ui/Button.svelte";
  import type { AppStore } from "../store/appStore.svelte";

  let { store }: { store: AppStore } = $props();
</script>

<Card title="Project" subtitle="Choose a built ProjectOS project.">
  <select
    class="pos-input"
    value={store.projectId}
    onchange={(e) => store.selectProject((e.currentTarget as HTMLSelectElement).value)}
  >
    <option value="">Select project</option>
    {#each store.projects as project}
      <option value={project.project_id}>
        {project.name} ({project.project_id})
      </option>
    {/each}
  </select>

  <div class="pos-actions">
    <Button onclick={() => store.refreshProjects()}>Refresh projects</Button>
  </div>

  {#if store.projectId}
    <div class="pos-project-summary">
      <span>Selected</span>
      <strong>{store.plugin.settings.projectName || store.projectId}</strong>
      <code>{store.projectId}</code>
    </div>
  {:else if !store.projects.length}
    <div class="pos-empty">No backend projects found.</div>
  {/if}
</Card>
