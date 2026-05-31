<script lang="ts">
  import { fly } from "svelte/transition";
  import Card from "../ui/Card.svelte";
  import Button from "../ui/Button.svelte";
  import Tabs from "../ui/Tabs.svelte";
  import StatusPill from "../ui/StatusPill.svelte";
  import type { AppStore } from "../store/appStore.svelte";

  let { store }: { store: AppStore } = $props();
  let query = $state("");
  const r = $derived(store.simulation);
  const changes = $derived(r?.applied_graph_changes ?? {});
  const recommendations = $derived(r?.report?.recommendations ?? r?.cv_improvements?.bullets ?? []);
</script>

<Card title="Simulation" subtitle="Persona simulation and reports.">
  <textarea class="pos-textarea" rows="4" placeholder="Query, CV goal, or report request" bind:value={query}></textarea>
  <div class="pos-actions">
    <Button variant="primary" onclick={() => store.runSimulation(query)}>Run simulation</Button>
    <Button onclick={() => store.loadSimulation()}>Load result</Button>
  </div>
  {#if store.simulationLive}<p class="pos-muted pos-runtime-note">{store.simulationLive}</p>{/if}

  {#if r}
    <Tabs tabs={["Report", "Agents", "Timeline", "CV"]}>
      {#snippet children(tab)}
        {#if tab === "Report"}
          <div class="pos-summary">
            <div class="pos-summary-title">{r.report?.title || "Simulation report"}</div>
            <p>{r.report?.answer || r.environment?.objective || "No report."}</p>
            <span class="pos-meta">Graph changes: +{changes.nodes_added ?? 0} nodes, +{changes.edges_added ?? 0} edges</span>
          </div>
          {#if recommendations.length}
            <div class="pos-summary-title">Recommendations</div>
            {#each recommendations as rec}<div class="pos-suggestion">{rec}</div>{/each}
          {/if}
        {:else if tab === "Agents"}
          {#if !(r.personas?.length)}<p class="pos-muted">No persona agents.</p>{/if}
          {#each r.personas ?? [] as persona, i}
            <div class="pos-issue" in:fly={{ y: 8, delay: i * 40, duration: 200 }}>
              <strong>{persona.name || "Agent"} ({persona.agent_id || ""})</strong>
              <p>{persona.role || ""}</p>
              {#each [...(persona.goals ?? []), ...(persona.knowledge ?? [])].slice(0, 5) as goal}
                <div class="pos-suggestion">{goal}</div>
              {/each}
            </div>
          {/each}
        {:else if tab === "Timeline"}
          {#if !(r.timeline?.length)}<p class="pos-muted">No agent timeline.</p>{/if}
          {#each r.timeline ?? [] as event, i}
            <div class="pos-timeline-item" in:fly={{ y: 8, delay: i * 30, duration: 200 }}>
              <StatusPill state="running" label={`Round ${event.round ?? "?"} · ${event.agent_id ?? "agent"}`} />
              <p>{event.observation || ""}</p>
              <div class="pos-suggestion">{event.proposal || ""}</div>
            </div>
          {/each}
        {:else if tab === "CV"}
          {#if r.cv_improvements?.improved_draft}
            <div class="pos-summary-title">Improved draft</div>
            <pre class="pos-draft">{r.cv_improvements.improved_draft}</pre>
          {:else}
            <p class="pos-muted">{r.cv_improvements?.summary || "No CV draft."}</p>
          {/if}
        {/if}
      {/snippet}
    </Tabs>
  {/if}
</Card>
