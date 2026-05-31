<script lang="ts">
  import type { Snippet } from "svelte";
  let { title, subtitle, header, children }: {
    title: string;
    subtitle?: string;
    header?: Snippet;
    children: Snippet;
  } = $props();
</script>

<section class="pos-card">
  <div class="pos-card-head">
    <div>
      <h3>{title}</h3>
      {#if subtitle}<p class="pos-muted">{subtitle}</p>{/if}
    </div>
    {#if header}<div class="pos-card-head-extra">{@render header()}</div>{/if}
  </div>
  <div class="pos-card-body">{@render children()}</div>
</section>
