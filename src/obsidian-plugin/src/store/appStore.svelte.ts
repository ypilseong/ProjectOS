import { Notice } from "obsidian";

import { ApiClient } from "../api/client";
import { AnalysisResult, ProjectSummary, SimulationResult, TaskUpdate } from "../api/types";
import { BackendSettings, DEFAULT_BACKEND_SETTINGS, mergeBackendSettings } from "../lib/runtime";

export interface PluginBridge {
  settings: { baseUrl: string; projectId: string; projectName: string; targetFolder: string };
  saveSettings(): Promise<void>;
}

export class AppStore {
  status = $state("Idle");
  task = $state<TaskUpdate | null>(null);
  projects = $state<ProjectSummary[]>([]);
  backendSettings = $state<BackendSettings>({ ...DEFAULT_BACKEND_SETTINGS });
  runtimeDirty = $state(false);
  analysis = $state<AnalysisResult | null>(null);
  simulation = $state<SimulationResult | null>(null);
  simulationLive = $state("");
  answer = $state("");

  constructor(
    public client: ApiClient,
    public plugin: PluginBridge,
  ) {}

  get projectId(): string {
    return this.plugin.settings.projectId.trim();
  }

  requireProjectId(): string | null {
    if (!this.projectId) {
      new Notice("Create or select a ProjectOS project first.");
      return null;
    }
    return this.projectId;
  }

  targetFolder(): string {
    const explicit = this.plugin.settings.targetFolder.trim();
    if (explicit) return explicit;
    const name = this.plugin.settings.projectName.trim() || this.projectId;
    return name ? `ProjectOS/${name}` : "ProjectOS";
  }

  private fail(message: string, error: unknown): void {
    this.status = message;
    new Notice(`${message} ${String(error)}`);
  }

  async refreshProjects(): Promise<void> {
    this.status = "Loading projects...";
    try {
      this.projects = await this.client.listProjects();
      this.status = this.projects.length ? "Projects loaded." : "No projects yet.";
    } catch (error) {
      this.projects = [];
      this.fail("Project list failed.", error);
    }
  }

  async selectProject(projectId: string): Promise<void> {
    if (!projectId) return;
    const match = this.projects.find((p) => p.project_id === projectId);
    this.plugin.settings.projectId = projectId;
    this.plugin.settings.projectName = match?.name ?? projectId;
    await this.plugin.saveSettings();
    this.status = `Selected ${this.plugin.settings.projectName}.`;
  }

  async createProject(name: string): Promise<void> {
    this.status = "Creating project...";
    try {
      const project = await this.client.createProject(name.trim() || "Obsidian Project");
      this.plugin.settings.projectId = project.project_id;
      this.plugin.settings.projectName = project.name;
      await this.plugin.saveSettings();
      await this.refreshProjects();
      this.status = `Created ${project.name}.`;
      new Notice(`ProjectOS project created: ${project.name}`);
    } catch (error) {
      this.fail("Project create failed.", error);
    }
  }

  async loadBackendSettings(): Promise<void> {
    try {
      this.backendSettings = await this.client.getBackendSettings();
      this.runtimeDirty = false;
    } catch (error) {
      this.backendSettings = { ...DEFAULT_BACKEND_SETTINGS };
      this.runtimeDirty = false;
      new Notice(`ProjectOS runtime settings unavailable: ${String(error)}`);
    }
  }

  applyPreset(settings: Partial<BackendSettings>): void {
    this.backendSettings = mergeBackendSettings({ ...this.backendSettings, ...settings });
    this.runtimeDirty = true;
  }

  markRuntimeDirty(): void {
    this.runtimeDirty = true;
  }

  async saveBackendSettings(): Promise<void> {
    this.status = "Saving runtime settings...";
    try {
      this.backendSettings = await this.client.setBackendSettings(this.backendSettings);
      this.runtimeDirty = false;
      this.status = "Runtime settings saved.";
      new Notice("ProjectOS runtime settings saved.");
    } catch (error) {
      this.fail("Runtime settings failed.", error);
    }
  }

  watch(taskId: string, onCompleted?: () => void, onUpdate?: (data: TaskUpdate) => void): void {
    this.client.watchTask(
      taskId,
      (data) => {
        this.task = data;
        this.status = `${data.progress ?? 0}% ${data.message ?? ""}`;
        onUpdate?.(data);
      },
      (status) => {
        if (status === "completed") onCompleted?.();
      },
      () => {
        this.task = null;
        this.status = "Task stream disconnected.";
      },
    );
  }

  async runAnalysis(): Promise<void> {
    const projectId = this.requireProjectId();
    if (!projectId) return;
    this.status = "Starting analysis...";
    try {
      const task = await this.client.startAnalysis(projectId);
      this.watch(task.task_id, () => this.loadAnalysis());
    } catch (error) {
      this.fail("Analysis failed.", error);
    }
  }

  async loadAnalysis(): Promise<void> {
    const projectId = this.requireProjectId();
    if (!projectId) return;
    this.status = "Loading analysis...";
    try {
      this.analysis = await this.client.getAnalysis(projectId);
      this.status = "Analysis loaded.";
    } catch (error) {
      this.fail("Analysis unavailable.", error);
    }
  }

  async runSimulation(query: string): Promise<void> {
    const projectId = this.requireProjectId();
    if (!projectId) return;
    this.status = "Starting simulation...";
    this.simulation = null;
    this.simulationLive = "Preparing local LLM persona simulation...";
    try {
      const task = await this.client.startSimulation(projectId, query);
      this.watch(
        task.task_id,
        () => this.loadSimulation(),
        (data) => {
          this.simulationLive = String(data.message ?? "Simulation running...");
        },
      );
    } catch (error) {
      this.simulationLive = "Simulation failed.";
      this.fail("Simulation failed.", error);
    }
  }

  async loadSimulation(): Promise<void> {
    const projectId = this.requireProjectId();
    if (!projectId) return;
    this.status = "Loading simulation...";
    try {
      this.simulation = await this.client.getSimulation(projectId);
      this.simulationLive = "Simulation result loaded.";
      this.status = "Simulation loaded.";
    } catch (error) {
      this.fail("Simulation unavailable.", error);
    }
  }

  async ask(question: string): Promise<void> {
    const projectId = this.requireProjectId();
    if (!projectId || !question.trim()) return;
    this.answer = "";
    this.status = "Asking...";
    try {
      await this.client.streamChat(projectId, question, (token) => {
        this.answer += token;
      });
      this.status = "Done.";
    } catch (error) {
      this.fail("Query failed.", error);
    }
  }
}
