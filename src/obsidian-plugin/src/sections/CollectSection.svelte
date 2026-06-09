<script lang="ts">
  import { Notice } from "obsidian";
  import Card from "../ui/Card.svelte";
  import Button from "../ui/Button.svelte";
  import type { AppStore } from "../store/appStore.svelte";

  let { store }: { store: AppStore } = $props();
  let files = $state<FileList | null>(null);
  let fileTypes = $state<Record<string, string>>({});

  const fileTypeOptions = [
    { value: "cv", label: "CV" },
    { value: "paper", label: "Paper" },
    { value: "report", label: "Report" },
    { value: "memo", label: "Memo" },
    { value: "note", label: "Note" },
  ];

  function inferFileType(filename: string): string {
    const lower = filename.toLowerCase();
    if (lower.includes("cv") || lower.includes("resume")) return "cv";
    if (lower.includes("paper") || lower.includes("publication")) return "paper";
    if (lower.includes("report")) return "report";
    if (lower.includes("memo") || lower.includes("note")) return "memo";
    return "note";
  }

  function setFiles(next: FileList | null): void {
    files = next;
    const nextTypes: Record<string, string> = {};
    for (const file of Array.from(next ?? [])) {
      nextTypes[file.name] = fileTypes[file.name] ?? inferFileType(file.name);
    }
    fileTypes = nextTypes;
  }

  function setFileType(filename: string, fileType: string): void {
    fileTypes = { ...fileTypes, [filename]: fileType };
  }

  async function uploadAndBuild(): Promise<void> {
    const projectId = store.requireProjectId();
    if (!projectId || !files || files.length === 0) return;
    store.status = "Uploading...";
    store.setWorkflowStep("collect", "running", "Uploading");
    store.setWorkflowStep("ontology", "idle");
    store.setWorkflowStep("graph", "idle");
    try {
      const parseTask = await store.client.uploadFiles(projectId, files, fileTypes);
      store.status = "Parsing uploaded files...";
      store.watch(parseTask.task_id, async () => {
        store.setWorkflowStep("collect", "success", "Parsed");
        store.status = "Building ontology...";
        store.setWorkflowStep("ontology", "running", "Starting");
        try {
          const ontologyTask = await store.client.startOntology(projectId);
          store.watch(ontologyTask.task_id, async () => {
            store.setWorkflowStep("ontology", "success", "Built");
            store.status = "Building graph...";
            store.setWorkflowStep("graph", "running", "Starting");
            try {
              const graphTask = await store.client.startGraphBuild(projectId);
              store.watch(graphTask.task_id, undefined, undefined, "graph");
            } catch (graphError) {
              store.setWorkflowStep("graph", "failed", "Start failed");
              store.status = "Graph build failed.";
              new Notice(`ProjectOS graph build failed: ${String(graphError)}`);
            }
          }, undefined, "ontology");
        } catch (ontologyError) {
          store.setWorkflowStep("ontology", "failed", "Start failed");
          store.status = "Ontology build failed.";
          new Notice(`ProjectOS ontology failed: ${String(ontologyError)}`);
        }
      }, undefined, "collect");
    } catch (error) {
      store.setWorkflowStep("collect", "failed", "Upload failed");
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
    onchange={(e) => setFiles((e.currentTarget as HTMLInputElement).files)}
  />
  {#if files?.length}
    <div class="pos-file-type-list">
      {#each Array.from(files) as file}
        <label class="pos-file-type-row">
          <span>{file.name}</span>
          <select
            value={fileTypes[file.name] ?? "note"}
            onchange={(e) => setFileType(file.name, (e.currentTarget as HTMLSelectElement).value)}
          >
            {#each fileTypeOptions as option}
              <option value={option.value}>{option.label}</option>
            {/each}
          </select>
        </label>
      {/each}
    </div>
  {/if}
  <Button onclick={uploadAndBuild}>Upload and build</Button>
</Card>
