<script lang="ts">
  import type { WorkflowStep } from "../store/appStore.svelte";

  let { steps }: { steps: WorkflowStep[] } = $props();
</script>

<div class="pos-workflow" aria-label="ProjectOS workflow">
  {#each steps as step, index}
    <div
      class="pos-workflow-step"
      class:is-running={step.status === "running"}
      class:is-success={step.status === "success"}
      class:is-failed={step.status === "failed"}
      class:is-skipped={step.status === "skipped"}
      title={step.message ?? step.label}
    >
      <span class="pos-workflow-dot">{index + 1}</span>
      <span class="pos-workflow-label">{step.label}</span>
    </div>
  {/each}
</div>
