<script lang="ts">
  import Card from "../ui/Card.svelte";
  import Button from "../ui/Button.svelte";
  import StatusPill from "../ui/StatusPill.svelte";
  import Disclosure from "../ui/Disclosure.svelte";
  import { RUNTIME_PRESETS, matchRuntimePreset, parsePositiveInt, DEFAULT_BACKEND_SETTINGS } from "../lib/runtime";
  import type { AppStore } from "../store/appStore.svelte";

  let { store }: { store: AppStore } = $props();

  const presetId = $derived(matchRuntimePreset(store.backendSettings));
  const presetTitle = $derived(
    presetId ? RUNTIME_PRESETS.find((p) => p.id === presetId)?.title : "Custom",
  );
  const note = $derived(
    store.backendSettings.graph_build_mode === "claude_task"
      ? "Claude Task mode runs without local LLM extraction and uses isolated task instructions."
      : store.backendSettings.graph_extraction_backend === "claude_code"
        ? "Chunk mode will call Claude Code for extraction batches. Increase chunk size to reduce calls."
        : "Chunk mode uses the local OpenAI-compatible endpoint for extraction.",
  );

  function setField<K extends keyof typeof store.backendSettings>(key: K, value: (typeof store.backendSettings)[K]): void {
    store.backendSettings = { ...store.backendSettings, [key]: value };
    store.markRuntimeDirty();
  }
</script>

<Card title="Runtime" subtitle="Current graph build backend.">
  {#snippet header()}
    <StatusPill state={store.runtimeDirty ? "running" : "done"} label={store.runtimeDirty ? "Unsaved" : "Saved"} />
  {/snippet}

  <div class="pos-runtime-state">
    <span class="pos-runtime-label">{presetTitle} / {store.backendSettings.graph_build_mode}</span>
  </div>

  <Disclosure label="Runtime settings">
    <div class="pos-presets">
      {#each RUNTIME_PRESETS as preset}
        <button
          class="pos-preset"
          class:is-active={preset.id === presetId}
          onclick={() => store.applyPreset(preset.settings)}
        >
          <strong>{preset.title}</strong>
          <span>{preset.description}</span>
        </button>
      {/each}
    </div>

    <label class="pos-field-label">LLM backend</label>
    <select class="pos-input" value={store.backendSettings.llm_backend} onchange={(e) => setField("llm_backend", (e.currentTarget as HTMLSelectElement).value)}>
      <option value="local">Local LLM</option>
      <option value="claude_code">Claude Code</option>
    </select>

    <label class="pos-field-label">Graph build mode</label>
    <select class="pos-input" value={store.backendSettings.graph_build_mode} onchange={(e) => setField("graph_build_mode", (e.currentTarget as HTMLSelectElement).value)}>
      <option value="chunk">Chunk extraction</option>
      <option value="claude_task">Claude task mode</option>
    </select>

    <label class="pos-field-label">Chunk extraction backend</label>
    <select class="pos-input" value={store.backendSettings.graph_extraction_backend} onchange={(e) => setField("graph_extraction_backend", (e.currentTarget as HTMLSelectElement).value)}>
      <option value="local">Local LLM</option>
      <option value="claude_code">Claude Code</option>
    </select>

    <div class="pos-field-grid">
      <div>
        <label class="pos-field-label">Claude Code model</label>
        <input class="pos-input" type="text" placeholder="claude-haiku-4-5" value={store.backendSettings.claude_code_model} oninput={(e) => setField("claude_code_model", (e.currentTarget as HTMLInputElement).value.trim())} />
      </div>
      <div>
        <label class="pos-field-label">Chunk size</label>
        <input class="pos-input" type="number" placeholder="500" value={store.backendSettings.chunk_size} oninput={(e) => setField("chunk_size", parsePositiveInt((e.currentTarget as HTMLInputElement).value, DEFAULT_BACKEND_SETTINGS.chunk_size))} />
      </div>
      <div>
        <label class="pos-field-label">Chunk overlap</label>
        <input class="pos-input" type="number" placeholder="50" value={store.backendSettings.chunk_overlap} oninput={(e) => setField("chunk_overlap", parsePositiveInt((e.currentTarget as HTMLInputElement).value, DEFAULT_BACKEND_SETTINGS.chunk_overlap))} />
      </div>
    </div>

    <p class="pos-muted pos-runtime-note">{note}</p>

    <div class="pos-actions">
      <Button onclick={() => store.loadBackendSettings()}>Reload</Button>
      <Button variant="primary" onclick={() => store.saveBackendSettings()}>Save runtime</Button>
    </div>
  </Disclosure>
</Card>
