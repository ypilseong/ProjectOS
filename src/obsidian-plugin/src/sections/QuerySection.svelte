<script lang="ts">
  import Card from "../ui/Card.svelte";
  import Button from "../ui/Button.svelte";
  import type { AppStore } from "../store/appStore.svelte";

  let { store }: { store: AppStore } = $props();
  let question = $state("");
</script>

<Card title="Query" subtitle="Ask through ProjectOS QueryAgent.">
  <textarea class="pos-textarea" rows="4" bind:value={question}></textarea>
  <Button onclick={() => store.ask(question)}>Ask</Button>
  {#if store.answer}<div class="pos-answer">{store.answer}</div>{/if}
</Card>
