import { Notice } from "obsidian";
import { createSubscriber } from "svelte/reactivity";

import { ApiClient } from "../api/client";
import { AnalysisResult, ProjectSummary, SimulationResult, TaskUpdate } from "../api/types";
import { BackendSettings, DEFAULT_BACKEND_SETTINGS, mergeBackendSettings } from "../lib/runtime";
import { deletionTargetFolder, projectTargetFolder } from "../lib/vaultSync";

export type WorkflowStepStatus = "idle" | "running" | "success" | "failed" | "skipped";

export interface WorkflowStep {
  id: string;
  label: string;
  status: WorkflowStepStatus;
  message?: string;
}

export interface PluginBridge {
  settings: { baseUrl: string; projectId: string; projectName: string; targetFolder: string };
  saveSettings(): Promise<void>;
  deleteProjectFolder(targetFolder: string): Promise<boolean>;
}

const DEFAULT_WORKFLOW: WorkflowStep[] = [
  { id: "project", label: "Project", status: "idle" },
  { id: "runtime", label: "Runtime", status: "idle" },
  { id: "sync", label: "Sync", status: "idle" },
  { id: "collect", label: "Collect", status: "idle" },
  { id: "ontology", label: "Ontology", status: "idle" },
  { id: "graph", label: "Graph", status: "idle" },
  { id: "analysis", label: "Analysis", status: "idle" },
  { id: "query", label: "Query", status: "idle" },
  { id: "simulation", label: "Sim", status: "idle" },
];

export class AppStore {
  private notify = (): void => {};
  private subscribe = createSubscriber((update) => {
    this.notify = update;
    return () => {
      this.notify = (): void => {};
    };
  });

  private _status = "Idle";
  private _task: TaskUpdate | null = null;
  private _projects: ProjectSummary[] = [];
  private _backendSettings: BackendSettings = { ...DEFAULT_BACKEND_SETTINGS };
  private _runtimeDirty = false;
  private _analysis: AnalysisResult | null = null;
  private _simulation: SimulationResult | null = null;
  private _simulationLive = "";
  private _answer = "";
  private _workflow = DEFAULT_WORKFLOW.map((step) => ({ ...step }));

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

  get task(): TaskUpdate | null {
    this.subscribe();
    return this._task;
  }

  set task(value: TaskUpdate | null) {
    this._task = value;
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

  get backendSettings(): BackendSettings {
    this.subscribe();
    return this._backendSettings;
  }

  set backendSettings(value: BackendSettings) {
    this._backendSettings = value;
    this.notify();
  }

  get runtimeDirty(): boolean {
    this.subscribe();
    return this._runtimeDirty;
  }

  set runtimeDirty(value: boolean) {
    this._runtimeDirty = value;
    this.notify();
  }

  get analysis(): AnalysisResult | null {
    this.subscribe();
    return this._analysis;
  }

  set analysis(value: AnalysisResult | null) {
    this._analysis = value;
    this.notify();
  }

  get simulation(): SimulationResult | null {
    this.subscribe();
    return this._simulation;
  }

  set simulation(value: SimulationResult | null) {
    this._simulation = value;
    this.notify();
  }

  get simulationLive(): string {
    this.subscribe();
    return this._simulationLive;
  }

  set simulationLive(value: string) {
    this._simulationLive = value;
    this.notify();
  }

  get answer(): string {
    this.subscribe();
    return this._answer;
  }

  set answer(value: string) {
    this._answer = value;
    this.notify();
  }

  get workflow(): WorkflowStep[] {
    this.subscribe();
    return this._workflow;
  }

  set workflow(value: WorkflowStep[]) {
    this._workflow = value;
    this.notify();
  }

  get projectId(): string {
    this.subscribe();
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
    return projectTargetFolder(this.plugin.settings);
  }

  private fail(message: string, error: unknown): void {
    this.status = message;
    new Notice(`${message} ${String(error)}`);
  }

  setWorkflowStep(id: string, status: WorkflowStepStatus, message?: string): void {
    this.workflow = this.workflow.map((step) =>
      step.id === id ? { ...step, status, message } : step,
    );
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
    this.setWorkflowStep("project", "success", this.plugin.settings.projectName);
    this.status = `Selected ${this.plugin.settings.projectName}.`;
  }

  async createProject(name: string): Promise<void> {
    this.status = "Creating project...";
    this.setWorkflowStep("project", "running", "Creating");
    try {
      const project = await this.client.createProject(name.trim() || "Obsidian Project");
      this.plugin.settings.projectId = project.project_id;
      this.plugin.settings.projectName = project.name;
      await this.plugin.saveSettings();
      await this.refreshProjects();
      this.setWorkflowStep("project", "success", project.name);
      this.status = `Created ${project.name}.`;
      new Notice(`ProjectOS project created: ${project.name}`);
    } catch (error) {
      this.setWorkflowStep("project", "failed", "Create failed");
      this.fail("Project create failed.", error);
    }
  }

  async deleteProject(projectId: string): Promise<void> {
    const project = this.projects.find((p) => p.project_id === projectId);
    const label = project?.name ?? projectId;
    if (!projectId) return;
    const localFolder = deletionTargetFolder(this.plugin.settings, projectId, label);
    if (!window.confirm(
      `Delete ProjectOS project "${label}"? This removes backend data and local vault folder "${localFolder}".`,
    )) return;

    this.status = "Deleting project...";
    try {
      await this.client.deleteProject(projectId);
      const removedLocalFolder = await this.plugin.deleteProjectFolder(localFolder);
      if (this.plugin.settings.projectId === projectId) {
        this.plugin.settings.projectId = "";
        this.plugin.settings.projectName = "";
        this.analysis = null;
        this.simulation = null;
        this.answer = "";
        this.setWorkflowStep("project", "idle");
        await this.plugin.saveSettings();
      }
      await this.refreshProjects();
      this.status = `Deleted ${label}.`;
      new Notice(
        removedLocalFolder
          ? `ProjectOS project deleted: ${label}; removed ${localFolder}.`
          : `ProjectOS project deleted: ${label}; no local folder found at ${localFolder}.`,
      );
    } catch (error) {
      this.fail("Project delete failed.", error);
    }
  }

  async loadBackendSettings(): Promise<void> {
    try {
      this.backendSettings = await this.client.getBackendSettings();
      this.runtimeDirty = false;
      this.setWorkflowStep("runtime", "success", this.backendSettings.graph_build_mode);
    } catch (error) {
      this.backendSettings = { ...DEFAULT_BACKEND_SETTINGS };
      this.runtimeDirty = false;
      this.setWorkflowStep("runtime", "failed", "Unavailable");
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
    this.setWorkflowStep("runtime", "running", "Saving");
    try {
      this.backendSettings = await this.client.setBackendSettings(this.backendSettings);
      this.runtimeDirty = false;
      this.setWorkflowStep("runtime", "success", this.backendSettings.graph_build_mode);
      this.status = "Runtime settings saved.";
      new Notice("ProjectOS runtime settings saved.");
    } catch (error) {
      this.setWorkflowStep("runtime", "failed", "Save failed");
      this.fail("Runtime settings failed.", error);
    }
  }

  watch(
    taskId: string,
    onCompleted?: () => void,
    onUpdate?: (data: TaskUpdate) => void,
    workflowStepId?: string,
  ): void {
    this.client.watchTask(
      taskId,
      (data) => {
        this.task = data;
        this.status = `${data.progress ?? 0}% ${data.message ?? ""}`;
        if (workflowStepId) {
          const nextStatus = data.status === "failed"
            ? "failed"
            : data.status === "completed"
              ? "success"
              : "running";
          this.setWorkflowStep(workflowStepId, nextStatus, data.message);
        }
        onUpdate?.(data);
      },
      (status) => {
        if (status === "completed") onCompleted?.();
      },
      () => {
        this.task = null;
        if (workflowStepId) this.setWorkflowStep(workflowStepId, "failed", "Stream disconnected");
        this.status = "Task stream disconnected.";
      },
    );
  }

  async runAnalysis(): Promise<void> {
    const projectId = this.requireProjectId();
    if (!projectId) return;
    this.status = "Starting analysis...";
    this.setWorkflowStep("analysis", "running", "Starting");
    try {
      const task = await this.client.startAnalysis(projectId);
      this.watch(task.task_id, () => this.loadAnalysis(), undefined, "analysis");
    } catch (error) {
      this.setWorkflowStep("analysis", "failed", "Start failed");
      this.fail("Analysis failed.", error);
    }
  }

  async loadAnalysis(): Promise<void> {
    const projectId = this.requireProjectId();
    if (!projectId) return;
    this.status = "Loading analysis...";
    try {
      this.analysis = await this.client.getAnalysis(projectId);
      this.setWorkflowStep("analysis", "success", "Loaded");
      this.status = "Analysis loaded.";
    } catch (error) {
      this.setWorkflowStep("analysis", "failed", "Load failed");
      this.fail("Analysis unavailable.", error);
    }
  }

  async runSimulation(query: string): Promise<void> {
    const projectId = this.requireProjectId();
    if (!projectId) return;
    this.status = "Starting simulation...";
    this.setWorkflowStep("simulation", "running", "Starting");
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
        "simulation",
      );
    } catch (error) {
      this.setWorkflowStep("simulation", "failed", "Start failed");
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
      this.setWorkflowStep("simulation", "success", "Loaded");
      this.status = "Simulation loaded.";
    } catch (error) {
      this.setWorkflowStep("simulation", "failed", "Load failed");
      this.fail("Simulation unavailable.", error);
    }
  }

  async ask(question: string): Promise<void> {
    const projectId = this.requireProjectId();
    if (!projectId || !question.trim()) return;
    this.answer = "";
    this.status = "Asking...";
    this.setWorkflowStep("query", "running", "Streaming");
    try {
      await this.client.streamChat(projectId, question, (token) => {
        this.answer += token;
      });
      this.setWorkflowStep("query", "success", "Answered");
      this.status = "Done.";
    } catch (error) {
      this.setWorkflowStep("query", "failed", "Query failed");
      this.fail("Query failed.", error);
    }
  }
}
