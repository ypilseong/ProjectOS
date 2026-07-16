import { Notice } from "obsidian";
import { createSubscriber } from "svelte/reactivity";

import { ApiClient } from "../api/client";
import type { ProjectSummary } from "../api/types";
import { projectTargetFolder } from "../lib/vaultSync";

export interface PluginBridge {
  settings: {
    baseUrl: string;
    projectId: string;
    projectName: string;
    targetFolder: string;
  };
  saveSettings(): Promise<void>;
}

export class AppStore {
  private notify = (): void => {};
  private subscribe = createSubscriber((update) => {
    this.notify = update;
    return () => {
      this.notify = (): void => {};
    };
  });

  private _status = "Idle";
  private _projects: ProjectSummary[] = [];

  constructor(
    public client: ApiClient,
    public plugin: PluginBridge,
  ) {}

  get status(): string {
    this.subscribe();
    return this._status;
  }

  set status(value: string) {
    this._status = value;
    this.notify();
  }

  get projects(): ProjectSummary[] {
    this.subscribe();
    return this._projects;
  }

  set projects(value: ProjectSummary[]) {
    this._projects = value;
    this.notify();
  }

  get projectId(): string {
    this.subscribe();
    return this.plugin.settings.projectId.trim();
  }

  requireProjectId(): string | null {
    if (!this.projectId) {
      new Notice("Select a ProjectOS project first.");
      return null;
    }
    return this.projectId;
  }

  targetFolder(): string {
    return projectTargetFolder(this.plugin.settings);
  }

  async refreshProjects(): Promise<void> {
    this.status = "Loading projects...";
    try {
      this.projects = await this.client.listProjects();
      this.status = this.projects.length ? "Projects loaded." : "No projects found.";
    } catch (error) {
      this.projects = [];
      this.status = "Project list failed.";
      new Notice(`ProjectOS project list failed: ${String(error)}`);
    }
  }

  async selectProject(projectId: string): Promise<void> {
    const match = this.projects.find((project) => project.project_id === projectId);
    this.plugin.settings.projectId = projectId;
    this.plugin.settings.projectName = match?.name ?? projectId;
    await this.plugin.saveSettings();
    this.status = projectId ? `Selected ${this.plugin.settings.projectName}.` : "No project selected.";
  }
}
