<script lang="ts">
  let { state = "idle", label }: {
    state?: "idle" | "running" | "done" | "error";
    label: string;
  } = $props();
</script>

<span class="pos-pill pos-pill-{state}">{label}</span>
