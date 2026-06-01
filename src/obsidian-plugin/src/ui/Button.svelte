<script lang="ts">
  import type { Snippet } from "svelte";
  let { variant = "default", disabled = false, onclick, children }: {
    variant?: "default" | "primary" | "danger";
    disabled?: boolean;
    onclick?: () => void;
    children: Snippet;
  } = $props();
</script>

<button class="pos-btn pos-btn-{variant}" {disabled} {onclick}>{@render children()}</button>
