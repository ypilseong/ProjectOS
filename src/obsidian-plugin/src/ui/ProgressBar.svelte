<script lang="ts">
  let { progress = 0, active = false }: { progress?: number; active?: boolean } = $props();
</script>

{#if active}
  <div class="pos-progress">
    <div class="pos-progress-fill" style:width={`${Math.max(0, Math.min(100, progress))}%`}></div>
  </div>
{/if}
