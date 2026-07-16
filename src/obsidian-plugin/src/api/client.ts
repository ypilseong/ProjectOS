import type { ProjectSummary } from "./types";
import type { VaultPayload } from "../lib/vaultSync";

export class ApiClient {
  constructor(private getBaseUrl: () => string) {}

  private url(path: string): string {
    return `${this.getBaseUrl().replace(/\/+$/, "")}${path}`;
  }

  private async json<T>(path: string): Promise<T> {
    const response = await fetch(this.url(path));
    if (!response.ok) throw new Error(await response.text());
    return (await response.json()) as T;
  }

  listProjects(): Promise<ProjectSummary[]> {
    return this.json<ProjectSummary[]>("/api/projects");
  }

  exportVault(projectId: string): Promise<VaultPayload> {
    return this.json<VaultPayload>(`/api/projects/${projectId}/vault/export`);
  }
}
