import { BackendSettings, mergeBackendSettings } from "../lib/runtime";
import { AnalysisResult, ProjectSummary, SimulationResult, TaskUpdate } from "./types";
import type { VaultPayload } from "../lib/vaultSync";

export class ApiClient {
  constructor(private getBaseUrl: () => string) {}

  private url(path: string): string {
    return `${this.getBaseUrl().replace(/\/+$/, "")}${path}`;
  }

  private async json<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(this.url(path), init);
    if (!response.ok) throw new Error(await response.text());
    return (await response.json()) as T;
  }

  listProjects(): Promise<ProjectSummary[]> {
    return this.json<ProjectSummary[]>("/api/projects");
  }

  createProject(name: string): Promise<ProjectSummary> {
    return this.json<ProjectSummary>("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, description: "Created from Obsidian" }),
    });
  }

  async getBackendSettings(): Promise<BackendSettings> {
    return mergeBackendSettings(await this.json<Partial<BackendSettings>>("/api/settings"));
  }

  async setBackendSettings(settings: BackendSettings): Promise<BackendSettings> {
    return mergeBackendSettings(
      await this.json<Partial<BackendSettings>>("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      }),
    );
  }

  exportVault(projectId: string): Promise<VaultPayload> {
    return this.json<VaultPayload>(`/api/projects/${projectId}/vault/export`);
  }

  async uploadFiles(projectId: string, files: FileList): Promise<void> {
    const form = new FormData();
    Array.from(files).forEach((file) => form.append("files", file));
    form.append("file_type", "note");
    const response = await fetch(this.url(`/api/projects/${projectId}/files`), {
      method: "POST",
      body: form,
    });
    if (!response.ok) throw new Error(await response.text());
  }

  startGraphBuild(projectId: string): Promise<{ task_id: string }> {
    return this.json<{ task_id: string }>(`/api/projects/${projectId}/graph`, { method: "POST" });
  }

  startAnalysis(projectId: string): Promise<{ task_id: string }> {
    return this.json<{ task_id: string }>(`/api/projects/${projectId}/analysis`, { method: "POST" });
  }

  getAnalysis(projectId: string): Promise<AnalysisResult> {
    return this.json<AnalysisResult>(`/api/projects/${projectId}/analysis`);
  }

  startSimulation(projectId: string, query: string): Promise<{ task_id: string }> {
    return this.json<{ task_id: string }>(`/api/projects/${projectId}/simulation`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: query.trim(), apply_graph: true, update_vault: true }),
    });
  }

  getSimulation(projectId: string): Promise<SimulationResult> {
    return this.json<SimulationResult>(`/api/projects/${projectId}/simulation`);
  }

  watchTask(
    taskId: string,
    onUpdate: (data: TaskUpdate) => void,
    onDone: (status: string) => void,
    onError: () => void,
  ): EventSource {
    const events = new EventSource(this.url(`/api/tasks/${taskId}/stream`));
    events.onmessage = (event) => {
      const data = JSON.parse(event.data) as TaskUpdate;
      onUpdate(data);
      if (data.status === "completed" || data.status === "failed") {
        events.close();
        onDone(data.status);
      }
    };
    events.onerror = () => {
      events.close();
      onError();
    };
    return events;
  }

  async streamChat(projectId: string, question: string, onToken: (token: string) => void): Promise<void> {
    const response = await fetch(this.url(`/api/projects/${projectId}/chat`), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    if (!response.ok || !response.body) throw new Error(await response.text());
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop() ?? "";
      for (const event of events) {
        const line = event.split("\n").find((part) => part.startsWith("data: "));
        if (!line) continue;
        const data = JSON.parse(line.slice(6));
        if (data.token) onToken(data.token);
      }
    }
  }
}
