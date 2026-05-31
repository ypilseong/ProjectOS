<script lang="ts">
  import { Notice } from "obsidian";
  import Card from "../ui/Card.svelte";
  import Button from "../ui/Button.svelte";
  import type { AppStore } from "../store/appStore.svelte";

  let { store }: { store: AppStore } = $props();
  let files = $state<FileList | null>(null);

  async function uploadAndBuild(): Promise<void> {
    const projectId = store.requireProjectId();
    if (!projectId || !files || files.length === 0) return;
    store.status = "Uploading...";
    try {
      await store.client.uploadFiles(projectId, files);
      const task = await store.client.startGraphBuild(projectId);
      store.status = "Build started.";
      store.watch(task.task_id);
    } catch (error) {
      store.status = "Upload/build failed.";
      new Notice(`ProjectOS build failed: ${String(error)}`);
    }
  }
</script>

<Card title="Collect" subtitle="Upload files and start graph build.">
  <input
    class="pos-file"
    type="file"
    multiple
    onchange={(e) => (files = (e.currentTarget as HTMLInputElement).files)}
  />
  <Button onclick={uploadAndBuild}>Upload and build</Button>
</Card>
