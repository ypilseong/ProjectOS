<script lang="ts">
  import { slide } from "svelte/transition";
  import type { Snippet } from "svelte";
  let { label, open = false, children }: { label: string; open?: boolean; children: Snippet } = $props();
  const initialOpen = () => open;
  let expanded = $state(initialOpen());
</script>

<div class="pos-disclosure">
  <button class="pos-disclosure-summary" onclick={() => (expanded = !expanded)}>
    <span class="pos-disclosure-icon" class:open={expanded}>▶</span>{label}
  </button>
  {#if expanded}
    <div class="pos-disclosure-body" transition:slide={{ duration: 150 }}>{@render children()}</div>
  {/if}
</div>
