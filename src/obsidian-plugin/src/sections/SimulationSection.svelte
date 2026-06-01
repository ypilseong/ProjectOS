<script lang="ts">
  import { fly, slide } from "svelte/transition";
  import Card from "../ui/Card.svelte";
  import Button from "../ui/Button.svelte";
  import Tabs from "../ui/Tabs.svelte";
  import type { AppStore } from "../store/appStore.svelte";

  let { store }: { store: AppStore } = $props();
  let query = $state("");
  const r = $derived(store.simulation);
  const changes = $derived(r?.applied_graph_changes ?? {});
  const recommendations = $derived(r?.report?.recommendations ?? r?.cv_improvements?.bullets ?? []);

  const ROUND_COLORS = [
    "#4f8cff", "#2a9d8f", "#e9c46a", "#e76f51",
    "#9b5de5", "#f15bb5", "#00bbf9", "#43aa8b",
  ];
  function roundColor(n: number | undefined): string {
    const idx = ((n ?? 1) - 1) % ROUND_COLORS.length;
    return ROUND_COLORS[idx < 0 ? 0 : idx];
  }

  const roundGroups = $derived.by(() => {
    const map = new Map<number, Array<{ round?: number; agent_id?: string; observation?: string; proposal?: string }>>();
    for (const ev of r?.timeline ?? []) {
      const key = ev.round ?? 0;
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(ev);
    }
    return [...map.entries()].sort((a, b) => a[0] - b[0]);
  });

  function personaFor(agentId: string | undefined) {
    return (r?.personas ?? []).find((p) => p.agent_id === agentId);
  }
  function agentLabel(agentId: string | undefined): string {
    return personaFor(agentId)?.name || agentId || "agent";
  }

  let openItems = $state(new Set<string>());
  function toggleItem(key: string) {
    const next = new Set(openItems);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    openItems = next;
  }
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
          {#each roundGroups as [round, events], gi (round)}
            <div class="pos-round" style={`--round-color: ${roundColor(round)}`}>
              <div class="pos-round-head">Round {round}</div>
              {#each events as event, i (i)}
                {@const key = `${round}-${i}`}
                {@const persona = personaFor(event.agent_id)}
                <div class="pos-timeline-item" in:fly={{ y: 8, delay: gi * 80 + i * 40, duration: 200 }}>
                  <button
                    type="button"
                    class="pos-agent-btn"
                    class:is-open={openItems.has(key)}
                    onclick={() => toggleItem(key)}
                    disabled={!persona}
                  >
                    <span class="pos-agent-dot"></span>
                    {agentLabel(event.agent_id)}
                    {#if persona}<span class="pos-agent-caret">{openItems.has(key) ? "▾" : "▸"}</span>{/if}
                  </button>
                  {#if persona && openItems.has(key)}
                    <div class="pos-agent-desc" transition:slide={{ duration: 150 }}>
                      <div class="pos-agent-role">{persona.role || persona.agent_id}</div>
                      {#each [...(persona.goals ?? []), ...(persona.knowledge ?? [])].slice(0, 5) as detail}
                        <div class="pos-suggestion">{detail}</div>
                      {/each}
                    </div>
                  {/if}
                  <p>{event.observation || ""}</p>
                  <div class="pos-suggestion">{event.proposal || ""}</div>
                </div>
              {/each}
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
