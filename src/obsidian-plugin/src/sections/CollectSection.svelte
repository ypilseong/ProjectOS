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
      const parseTask = await store.client.uploadFiles(projectId, files);
      store.status = "Parsing uploaded files...";
      store.watch(parseTask.task_id, async () => {
        store.status = "Building ontology...";
        try {
          const ontologyTask = await store.client.startOntology(projectId);
          store.watch(ontologyTask.task_id, async () => {
            store.status = "Building graph...";
            try {
              const graphTask = await store.client.startGraphBuild(projectId);
              store.watch(graphTask.task_id);
            } catch (graphError) {
              store.status = "Graph build failed.";
              new Notice(`ProjectOS graph build failed: ${String(graphError)}`);
            }
          });
        } catch (ontologyError) {
          store.status = "Ontology build failed.";
          new Notice(`ProjectOS ontology failed: ${String(ontologyError)}`);
        }
      });
    } catch (error) {
      store.status = "Upload/build failed.";
      new Notice(`ProjectOS build failed: ${String(error)}`);
    }
  }
</script>

<Card title="Collect" subtitle="Upload files and build ontology and graph.">
  <input
    class="pos-file"
    type="file"
    multiple
    onchange={(e) => (files = (e.currentTarget as HTMLInputElement).files)}
  />
  <Button onclick={uploadAndBuild}>Upload and build</Button>
</Card>
