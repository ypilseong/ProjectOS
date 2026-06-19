<script lang="ts">
  import { Notice } from "obsidian";
  import Card from "../ui/Card.svelte";
  import Button from "../ui/Button.svelte";
  import { writePayloadToVault } from "../lib/graphColors";
  import type { App } from "obsidian";
  import type { AppStore } from "../store/appStore.svelte";

  let { store, app }: { store: AppStore; app: App } = $props();

  async function sync(): Promise<void> {
    const projectId = store.requireProjectId();
    if (!projectId) return;
    store.status = "Syncing...";
    try {
      const payload = await store.client.exportVault(projectId);
      const count = await writePayloadToVault(app, payload, store.targetFolder());
      store.status = `Synced ${count} notes.`;
      new Notice(`ProjectOS synced ${count} notes.`);
    } catch (error) {
      store.status = "Sync failed.";
      new Notice(`ProjectOS sync failed: ${String(error)}`);
    }
  }
</script>

<Card title="Sync" subtitle="Pull generated ProjectOS notes into this vault.">
  <div class="pos-sync-target">
    <span>Target folder</span>
    <code>{store.targetFolder()}</code>
  </div>
  <Button variant="primary" onclick={sync}>Sync selected project</Button>
</Card>
