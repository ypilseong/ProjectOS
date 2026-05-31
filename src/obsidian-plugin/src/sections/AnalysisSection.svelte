<script lang="ts">
  import Card from "../ui/Card.svelte";
  import Button from "../ui/Button.svelte";
  import type { AppStore } from "../store/appStore.svelte";

  let { store }: { store: AppStore } = $props();
  const a = $derived(store.analysis);
</script>

<Card title="Analysis" subtitle="Review uploaded documents and improvement points.">
  <div class="pos-actions">
    <Button onclick={() => store.runAnalysis()}>Run analysis</Button>
    <Button onclick={() => store.loadAnalysis()}>Load result</Button>
  </div>

  {#if a}
    <div class="pos-result">
      <div class="pos-summary">
        <div class="pos-summary-title">Summary</div>
        <p>{a.summary || "No summary."}</p>
        {#if a.generated_at}<span class="pos-meta">{new Date(a.generated_at).toLocaleString()}</span>{/if}
      </div>
      <div class="pos-summary-title">Improvement points</div>
      {#if !(a.issues?.length)}
        <p class="pos-muted">No issues found.</p>
      {/if}
      {#each a.issues ?? [] as issue}
        <div class="pos-issue">
          <span class="pos-severity pos-severity-{issue.severity ?? 'medium'}">{issue.severity ?? "medium"}</span>
          <strong>{issue.category ?? "Issue"}</strong>
          <p>{issue.description ?? ""}</p>
          <div class="pos-suggestion">{issue.suggestion ?? ""}</div>
        </div>
      {/each}
      {#if a.improved_draft}
        <div class="pos-summary-title">Improved draft</div>
        <pre class="pos-draft">{a.improved_draft}</pre>
      {/if}
    </div>
  {/if}
</Card>
