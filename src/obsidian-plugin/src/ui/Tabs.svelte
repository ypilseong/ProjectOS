<script lang="ts">
  import { fade } from "svelte/transition";
  import type { Snippet } from "svelte";
  let { tabs, children }: { tabs: string[]; children: Snippet<[string]> } = $props();
  const initialTab = () => tabs[0];
  let active = $state(initialTab());
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
