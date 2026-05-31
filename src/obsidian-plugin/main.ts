import {
  App,
  DropdownComponent,
  ItemView,
  Notice,
  Plugin,
  PluginSettingTab,
  Setting,
  TFile,
  TextComponent,
  WorkspaceLeaf,
} from "obsidian";

import {
  GENERATED_FOLDERS,
  buildVaultSyncPlan,
  type VaultPayload,
} from "./vaultSync";

const VIEW_TYPE_PROJECTOS = "projectos-vault-sync-view";

interface ProjectOSSettings {
  baseUrl: string;
  projectId: string;
  projectName: string;
  targetFolder: string;
}

interface ProjectSummary {
  project_id: string;
  name: string;
  description?: string;
  status?: string;
}

interface BackendSettings {
  llm_backend: string;
  graph_build_mode: string;
  graph_extraction_backend: string;
  claude_code_model: string;
  chunk_size: number;
  chunk_overlap: number;
}

const DEFAULT_SETTINGS: ProjectOSSettings = {
  baseUrl: "http://localhost:8002",
  projectId: "",
  projectName: "",
  targetFolder: "",
};

const DEFAULT_BACKEND_SETTINGS: BackendSettings = {
  llm_backend: "local",
  graph_build_mode: "chunk",
  graph_extraction_backend: "local",
  claude_code_model: "",
  chunk_size: 500,
  chunk_overlap: 50,
};

const RUNTIME_PRESETS: Array<{
  id: string;
  title: string;
  description: string;
  settings: Partial<BackendSettings>;
}> = [
  {
    id: "local",
    title: "Local",
    description: "Use the local OpenAI-compatible endpoint for graph extraction.",
    settings: {
      llm_backend: "local",
      graph_build_mode: "chunk",
      graph_extraction_backend: "local",
    },
  },
  {
    id: "hybrid",
    title: "Hybrid",
    description: "Use local extraction and Claude Code for higher quality maintenance.",
    settings: {
      llm_backend: "claude_code",
      graph_build_mode: "chunk",
      graph_extraction_backend: "local",
    },
  },
  {
    id: "claude_task",
    title: "Claude Task",
    description: "Run graph build through the isolated Claude Code task flow.",
    settings: {
      llm_backend: "claude_code",
      graph_build_mode: "claude_task",
      graph_extraction_backend: "claude_code",
      claude_code_model: "claude-haiku-4-5",
      chunk_size: 1800,
      chunk_overlap: 150,
    },
  },
];

function mergeBackendSettings(settings: Partial<BackendSettings>): BackendSettings {
  return { ...DEFAULT_BACKEND_SETTINGS, ...settings };
}

function parsePositiveInt(value: string, fallback: number): number {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

async function ensureFolder(app: App, path: string): Promise<void> {
  if (!path) return;
  const segments = path.split("/").filter(Boolean);
  let current = "";
  for (const segment of segments) {
    current = current ? `${current}/${segment}` : segment;
    if (!(await app.vault.adapter.exists(current))) {
      await app.vault.createFolder(current);
    }
  }
}

async function writeText(app: App, path: string, content: string): Promise<void> {
  const parent = path.split("/").slice(0, -1).join("/");
  await ensureFolder(app, parent);
  const existing = app.vault.getAbstractFileByPath(path);
  if (existing instanceof TFile) {
    await app.vault.modify(existing, content);
  } else {
    await app.vault.create(path, content);
  }
}

async function clearGenerated(app: App, targetFolder: string): Promise<void> {
  for (const folder of GENERATED_FOLDERS) {
    const path = [targetFolder, folder]
      .map((part) => part.trim().replace(/^\/+|\/+$/g, ""))
      .filter(Boolean)
      .join("/");
    if (await app.vault.adapter.exists(path)) {
      await app.vault.adapter.rmdir(path, true);
    }
  }
}

async function writePayloadToVault(
  app: App,
  payload: VaultPayload,
  targetFolder: string,
): Promise<number> {
  const plan = buildVaultSyncPlan(payload, targetFolder);
  await clearGenerated(app, targetFolder);
  for (const write of plan.writes) {
    await writeText(app, write.path, write.content);
  }
  return plan.noteCount;
}

export default class ProjectOSPlugin extends Plugin {
  settings: ProjectOSSettings = DEFAULT_SETTINGS;

  async onload(): Promise<void> {
    await this.loadSettings();
    this.registerView(VIEW_TYPE_PROJECTOS, (leaf) => new ProjectOSView(leaf, this));
    this.addRibbonIcon("network", "ProjectOS", () => this.activateView());
    this.addCommand({
      id: "open-projectos-panel",
      name: "Open ProjectOS panel",
      callback: () => this.activateView(),
    });
    this.addSettingTab(new ProjectOSSettingTab(this.app, this));
  }

  async loadSettings(): Promise<void> {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
  }

  async saveSettings(): Promise<void> {
    await this.saveData(this.settings);
  }

  async activateView(): Promise<void> {
    const { workspace } = this.app;
    let leaf: WorkspaceLeaf | null = workspace.getLeavesOfType(VIEW_TYPE_PROJECTOS)[0] ?? null;
    if (!leaf) {
      leaf = workspace.getRightLeaf(false);
      await leaf?.setViewState({ type: VIEW_TYPE_PROJECTOS, active: true });
    }
    if (leaf) workspace.revealLeaf(leaf);
  }

  apiUrl(path: string): string {
    return `${this.settings.baseUrl.replace(/\/+$/, "")}${path}`;
  }

  async getBackendSettings(): Promise<BackendSettings> {
    const response = await fetch(this.apiUrl("/api/settings"));
    if (!response.ok) throw new Error(await response.text());
    return mergeBackendSettings((await response.json()) as Partial<BackendSettings>);
  }

  async setBackendSettings(settings: BackendSettings): Promise<BackendSettings> {
    const response = await fetch(this.apiUrl("/api/settings"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    });
    if (!response.ok) throw new Error(await response.text());
    return mergeBackendSettings((await response.json()) as Partial<BackendSettings>);
  }
}

class ProjectOSSettingTab extends PluginSettingTab {
  plugin: ProjectOSPlugin;

  constructor(app: App, plugin: ProjectOSPlugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display(): void {
    const { containerEl } = this;
    containerEl.empty();

    new Setting(containerEl)
      .setName("Backend base URL")
      .addText((text) =>
        text
          .setPlaceholder("http://localhost:8002")
          .setValue(this.plugin.settings.baseUrl)
          .onChange(async (value) => {
            this.plugin.settings.baseUrl = value.trim() || DEFAULT_SETTINGS.baseUrl;
            await this.plugin.saveSettings();
          }),
      );

    new Setting(containerEl)
      .setName("Project ID")
      .setDesc("Auto-filled when a project is created or selected in the ProjectOS panel.")
      .addText((text) =>
        text
          .setPlaceholder("Created from the ProjectOS panel")
          .setValue(this.plugin.settings.projectId)
          .onChange(async (value) => {
            this.plugin.settings.projectId = value.trim();
            await this.plugin.saveSettings();
          }),
      );

    new Setting(containerEl)
      .setName("Target folder")
      .addText((text) =>
        text
          .setPlaceholder("ProjectOS")
          .setValue(this.plugin.settings.targetFolder)
          .onChange(async (value) => {
            this.plugin.settings.targetFolder = value.trim();
            await this.plugin.saveSettings();
          }),
      );

    this.renderRuntimeSettings(containerEl);
  }

  renderRuntimeSettings(containerEl: HTMLElement): void {
    const section = containerEl.createDiv({ cls: "projectos-settings-runtime" });
    section.createEl("h3", { text: "Backend runtime" });
    section.createEl("p", {
      cls: "projectos-muted",
      text: "These values are stored in the ProjectOS backend and affect the next graph build.",
    });

    let llmBackend: DropdownComponent;
    let graphMode: DropdownComponent;
    let graphBackend: DropdownComponent;
    let claudeModel: TextComponent;
    let chunkSize: TextComponent;
    let chunkOverlap: TextComponent;

    const setControls = (settings: Partial<BackendSettings>): void => {
      const merged = mergeBackendSettings(settings);
      llmBackend.setValue(merged.llm_backend);
      graphMode.setValue(merged.graph_build_mode);
      graphBackend.setValue(merged.graph_extraction_backend);
      claudeModel.setValue(merged.claude_code_model);
      chunkSize.setValue(String(merged.chunk_size));
      chunkOverlap.setValue(String(merged.chunk_overlap));
    };

    const readControls = (): BackendSettings => ({
      llm_backend: llmBackend.getValue(),
      graph_build_mode: graphMode.getValue(),
      graph_extraction_backend: graphBackend.getValue(),
      claude_code_model: claudeModel.getValue().trim(),
      chunk_size: parsePositiveInt(chunkSize.getValue(), DEFAULT_BACKEND_SETTINGS.chunk_size),
      chunk_overlap: parsePositiveInt(chunkOverlap.getValue(), DEFAULT_BACKEND_SETTINGS.chunk_overlap),
    });

    new Setting(section)
      .setName("Preset")
      .setDesc("Quickly switch the graph build behavior.")
      .addDropdown((dropdown) => {
        for (const preset of RUNTIME_PRESETS) dropdown.addOption(preset.id, preset.title);
        dropdown.onChange((value) => {
          const preset = RUNTIME_PRESETS.find((item) => item.id === value);
          if (preset) setControls(preset.settings);
        });
      });

    new Setting(section)
      .setName("LLM backend")
      .addDropdown((dropdown) => {
        llmBackend = dropdown
          .addOption("local", "Local LLM")
          .addOption("claude_code", "Claude Code");
      });

    new Setting(section)
      .setName("Graph build mode")
      .addDropdown((dropdown) => {
        graphMode = dropdown
          .addOption("chunk", "Chunk extraction")
          .addOption("claude_task", "Claude task mode");
      });

    new Setting(section)
      .setName("Chunk extraction backend")
      .addDropdown((dropdown) => {
        graphBackend = dropdown
          .addOption("local", "Local LLM")
          .addOption("claude_code", "Claude Code");
      });

    new Setting(section)
      .setName("Claude Code model")
      .addText((text) => {
        claudeModel = text.setPlaceholder("claude-haiku-4-5");
      });

    new Setting(section)
      .setName("Chunk size")
      .addText((text) => {
        chunkSize = text.setPlaceholder("1800");
      });

    new Setting(section)
      .setName("Chunk overlap")
      .addText((text) => {
        chunkOverlap = text.setPlaceholder("150");
      });

    new Setting(section)
      .addButton((button) =>
        button.setButtonText("Reload").onClick(async () => {
          try {
            setControls(await this.plugin.getBackendSettings());
            new Notice("ProjectOS runtime settings loaded.");
          } catch (error) {
            setControls(DEFAULT_BACKEND_SETTINGS);
            new Notice(`ProjectOS runtime settings unavailable: ${String(error)}`);
          }
        }),
      )
      .addButton((button) =>
        button
          .setButtonText("Save runtime")
          .setCta()
          .onClick(async () => {
            try {
              setControls(await this.plugin.setBackendSettings(readControls()));
              new Notice("ProjectOS runtime settings saved.");
            } catch (error) {
              new Notice(`ProjectOS runtime settings failed: ${String(error)}`);
            }
          }),
      );

    setControls(DEFAULT_BACKEND_SETTINGS);
    void this.plugin
      .getBackendSettings()
      .then(setControls)
      .catch(() => setControls(DEFAULT_BACKEND_SETTINGS));
  }
}

class ProjectOSView extends ItemView {
  plugin: ProjectOSPlugin;
  statusEl!: HTMLElement;
  answerEl!: HTMLElement;
  analysisEl!: HTMLElement;
  projectSelectEl!: HTMLSelectElement;
  projectNameInputEl!: HTMLInputElement;
  projectListEl!: HTMLElement;
  llmBackendSelectEl!: HTMLSelectElement;
  graphModeSelectEl!: HTMLSelectElement;
  graphBackendSelectEl!: HTMLSelectElement;
  claudeModelInputEl!: HTMLInputElement;
  chunkSizeInputEl!: HTMLInputElement;
  chunkOverlapInputEl!: HTMLInputElement;
  runtimeNoteEl!: HTMLElement;
  runtimeStateEl!: HTMLElement;
  runtimePresetButtons: HTMLButtonElement[] = [];

  constructor(leaf: WorkspaceLeaf, plugin: ProjectOSPlugin) {
    super(leaf);
    this.plugin = plugin;
  }

  getViewType(): string {
    return VIEW_TYPE_PROJECTOS;
  }

  getDisplayText(): string {
    return "ProjectOS";
  }

  async onOpen(): Promise<void> {
    const root = this.containerEl.children[1] as HTMLElement;
    root.empty();
    root.addClass("projectos-panel");

    root.createEl("h2", { text: "ProjectOS" });
    this.statusEl = root.createDiv({ text: "Idle" });

    this.renderProject(root);
    this.renderRuntimeSettings(root);
    this.renderSync(root);
    this.renderCollect(root);
    this.renderAnalysis(root);
    this.renderQuery(root);
    await this.loadBackendSettings();
    await this.refreshProjects();
  }

  createSection(root: HTMLElement, title: string, subtitle?: string): HTMLElement {
    const section = root.createDiv({ cls: "projectos-card" });
    const header = section.createDiv({ cls: "projectos-card-header" });
    header.createEl("h3", { text: title });
    if (subtitle) header.createEl("p", { text: subtitle });
    return section;
  }

  renderProject(root: HTMLElement): void {
    const section = this.createSection(root, "Project", "Create or select a backend project.");

    this.projectSelectEl = section.createEl("select");
    this.projectSelectEl.addClass("projectos-input");
    this.projectSelectEl.onchange = () => this.selectProject(this.projectSelectEl.value);

    this.projectNameInputEl = section.createEl("input", {
      type: "text",
      placeholder: "New project name",
    });
    this.projectNameInputEl.addClass("projectos-input");
    this.projectNameInputEl.value = this.plugin.settings.projectName;

    const actions = section.createDiv({ cls: "projectos-actions" });
    const refreshButton = section.createEl("button", { text: "Refresh" });
    refreshButton.addClass("projectos-button");
    refreshButton.onclick = () => this.refreshProjects();

    const createButton = section.createEl("button", { text: "Create project" });
    createButton.addClass("projectos-button");
    createButton.onclick = () => this.createProject();
    actions.append(refreshButton, createButton);

    this.projectListEl = section.createDiv({ cls: "projectos-project-list" });
  }

  renderRuntimeSettings(root: HTMLElement): void {
    const section = this.createSection(root, "Runtime", "Choose the graph build backend before uploading files.");

    this.runtimeStateEl = section.createDiv({ cls: "projectos-runtime-state" });
    this.renderRuntimePresets(section);

    this.llmBackendSelectEl = this.createSelect(this.createField(section, "LLM backend"), [
      ["local", "Local LLM"],
      ["claude_code", "Claude Code"],
    ]);

    this.graphModeSelectEl = this.createSelect(this.createField(section, "Graph build mode"), [
      ["chunk", "Chunk extraction"],
      ["claude_task", "Claude task mode"],
    ]);

    this.graphBackendSelectEl = this.createSelect(this.createField(section, "Chunk extraction backend"), [
      ["local", "Local LLM"],
      ["claude_code", "Claude Code"],
    ]);

    const grid = section.createDiv({ cls: "projectos-field-grid" });
    this.claudeModelInputEl = this.createInput(
      this.createField(grid, "Claude Code model"),
      "text",
      "claude-haiku-4-5",
    );
    this.chunkSizeInputEl = this.createInput(this.createField(grid, "Chunk size"), "number", "500");
    this.chunkOverlapInputEl = this.createInput(
      this.createField(grid, "Chunk overlap"),
      "number",
      "50",
    );

    this.llmBackendSelectEl.onchange = () => this.markRuntimeDirty();
    this.graphModeSelectEl.onchange = () => this.markRuntimeDirty();
    this.graphBackendSelectEl.onchange = () => this.markRuntimeDirty();
    this.claudeModelInputEl.oninput = () => this.markRuntimeDirty();
    this.chunkSizeInputEl.oninput = () => this.markRuntimeDirty();
    this.chunkOverlapInputEl.oninput = () => this.markRuntimeDirty();

    this.runtimeNoteEl = section.createDiv({ cls: "projectos-muted projectos-runtime-note" });

    const actions = section.createDiv({ cls: "projectos-actions" });
    const loadButton = actions.createEl("button", { text: "Reload" });
    loadButton.addClass("projectos-button");
    loadButton.onclick = () => this.loadBackendSettings();
    const saveButton = actions.createEl("button", { text: "Save runtime" });
    saveButton.addClass("projectos-button");
    saveButton.addClass("projectos-button-primary");
    saveButton.onclick = () => this.saveBackendSettings();
  }

  renderRuntimePresets(section: HTMLElement): void {
    const presets = section.createDiv({ cls: "projectos-runtime-presets" });
    this.runtimePresetButtons = [];
    for (const preset of RUNTIME_PRESETS) {
      const button = presets.createEl("button", { cls: "projectos-preset-button" });
      button.createEl("strong", { text: preset.title });
      button.createEl("span", { text: preset.description });
      button.onclick = () => {
        this.populateBackendSettings(preset.settings);
        this.markRuntimeDirty();
      };
      this.runtimePresetButtons.push(button);
    }
  }

  createField(parent: HTMLElement, labelText: string): HTMLElement {
    const field = parent.createDiv({ cls: "projectos-field" });
    field.createEl("label", { cls: "projectos-field-label", text: labelText });
    return field;
  }

  createSelect(parent: HTMLElement, options: Array<[string, string]>): HTMLSelectElement {
    const select = parent.createEl("select");
    select.addClass("projectos-input");
    for (const [value, label] of options) {
      select.createEl("option", { value, text: label });
    }
    return select;
  }

  createInput(parent: HTMLElement, type: string, placeholder: string): HTMLInputElement {
    const input = parent.createEl("input", { type, placeholder });
    input.addClass("projectos-input");
    return input;
  }

  backendSettingsFromInputs(): BackendSettings {
    return {
      llm_backend: this.llmBackendSelectEl.value,
      graph_build_mode: this.graphModeSelectEl.value,
      graph_extraction_backend: this.graphBackendSelectEl.value,
      claude_code_model: this.claudeModelInputEl.value.trim(),
      chunk_size: parsePositiveInt(this.chunkSizeInputEl.value, DEFAULT_BACKEND_SETTINGS.chunk_size),
      chunk_overlap: parsePositiveInt(
        this.chunkOverlapInputEl.value,
        DEFAULT_BACKEND_SETTINGS.chunk_overlap,
      ),
    };
  }

  populateBackendSettings(settings: Partial<BackendSettings>): void {
    const merged = mergeBackendSettings(settings);
    this.llmBackendSelectEl.value = merged.llm_backend;
    this.graphModeSelectEl.value = merged.graph_build_mode;
    this.graphBackendSelectEl.value = merged.graph_extraction_backend;
    this.claudeModelInputEl.value = merged.claude_code_model;
    this.chunkSizeInputEl.value = String(merged.chunk_size);
    this.chunkOverlapInputEl.value = String(merged.chunk_overlap);
    this.updateRuntimeNote();
    this.updateRuntimeState(merged, false);
  }

  updateRuntimeNote(): void {
    if (!this.runtimeNoteEl) return;
    if (this.graphModeSelectEl.value === "claude_task") {
      this.runtimeNoteEl.setText("Claude Task mode runs without local LLM extraction and uses isolated task instructions.");
    } else if (this.graphBackendSelectEl.value === "claude_code") {
      this.runtimeNoteEl.setText("Chunk mode will call Claude Code for extraction batches. Increase chunk size to reduce calls.");
    } else {
      this.runtimeNoteEl.setText("Chunk mode uses the local OpenAI-compatible endpoint for extraction.");
    }
  }

  updateRuntimeState(settings: BackendSettings, dirty: boolean): void {
    if (!this.runtimeStateEl) return;
    const presetId = this.matchRuntimePreset(settings);
    this.runtimeStateEl.empty();
    this.runtimeStateEl.createEl("span", {
      cls: "projectos-status-pill",
      text: dirty ? "Unsaved" : "Saved",
    });
    this.runtimeStateEl.createEl("span", {
      cls: "projectos-runtime-label",
      text: `${presetId ? RUNTIME_PRESETS.find((preset) => preset.id === presetId)?.title : "Custom"} / ${settings.graph_build_mode}`,
    });
    for (let index = 0; index < this.runtimePresetButtons.length; index += 1) {
      this.runtimePresetButtons[index].toggleClass("is-active", RUNTIME_PRESETS[index].id === presetId);
    }
  }

  matchRuntimePreset(settings: BackendSettings): string | null {
    for (const preset of RUNTIME_PRESETS) {
      const merged = mergeBackendSettings(preset.settings);
      if (
        merged.llm_backend === settings.llm_backend &&
        merged.graph_build_mode === settings.graph_build_mode &&
        merged.graph_extraction_backend === settings.graph_extraction_backend
      ) {
        return preset.id;
      }
    }
    return null;
  }

  markRuntimeDirty(): void {
    this.updateRuntimeNote();
    this.updateRuntimeState(this.backendSettingsFromInputs(), true);
  }

  async loadBackendSettings(): Promise<void> {
    try {
      this.populateBackendSettings(await this.plugin.getBackendSettings());
    } catch (error) {
      this.populateBackendSettings(DEFAULT_BACKEND_SETTINGS);
      new Notice(`ProjectOS runtime settings unavailable: ${String(error)}`);
    }
  }

  async saveBackendSettings(): Promise<void> {
    this.statusEl.setText("Saving runtime settings...");
    try {
      this.populateBackendSettings(await this.plugin.setBackendSettings(this.backendSettingsFromInputs()));
      this.statusEl.setText("Runtime settings saved.");
      new Notice("ProjectOS runtime settings saved.");
    } catch (error) {
      this.statusEl.setText("Runtime settings failed.");
      new Notice(`ProjectOS runtime settings failed: ${String(error)}`);
    }
  }

  renderSync(root: HTMLElement): void {
    const section = this.createSection(root, "Sync", "Pull generated notes into this vault.");
    const button = section.createEl("button", { text: "Pull from backend" });
    button.addClass("projectos-button");
    button.onclick = () => this.syncVault();
  }

  renderCollect(root: HTMLElement): void {
    const section = this.createSection(root, "Collect", "Upload files and start graph build.");
    const fileInput = section.createEl("input", { type: "file" });
    fileInput.addClass("projectos-file");
    fileInput.multiple = true;
    const button = section.createEl("button", { text: "Upload and build" });
    button.addClass("projectos-button");
    button.onclick = () => this.uploadAndBuild(fileInput.files);
  }

  renderAnalysis(root: HTMLElement): void {
    const section = this.createSection(root, "Analysis", "Review uploaded documents and improvement points.");
    const actions = section.createDiv({ cls: "projectos-actions" });
    const runButton = actions.createEl("button", { text: "Run analysis" });
    runButton.addClass("projectos-button");
    runButton.onclick = () => this.runAnalysis();

    const loadButton = actions.createEl("button", { text: "Load result" });
    loadButton.addClass("projectos-button");
    loadButton.onclick = () => this.loadAnalysis();

    this.analysisEl = section.createDiv({ cls: "projectos-analysis" });
  }

  renderQuery(root: HTMLElement): void {
    const section = this.createSection(root, "Query", "Ask through ProjectOS QueryAgent.");
    const input = section.createEl("textarea");
    input.addClass("projectos-textarea");
    input.rows = 4;
    const button = section.createEl("button", { text: "Ask" });
    button.addClass("projectos-button");
    this.answerEl = section.createDiv({ cls: "projectos-answer" });
    button.onclick = () => this.ask(input.value);
  }

  requireProjectId(): string | null {
    const projectId = this.plugin.settings.projectId.trim();
    if (!projectId) {
      new Notice("Create or select a ProjectOS project first.");
      return null;
    }
    return projectId;
  }

  targetFolderForCurrentProject(): string {
    if (this.plugin.settings.targetFolder.trim()) {
      return this.plugin.settings.targetFolder.trim();
    }
    const name = this.plugin.settings.projectName.trim() || this.plugin.settings.projectId.trim();
    return name ? `ProjectOS/${name}` : "ProjectOS";
  }

  async refreshProjects(): Promise<void> {
    this.statusEl.setText("Loading projects...");
    try {
      const response = await fetch(this.plugin.apiUrl("/api/projects"));
      if (!response.ok) throw new Error(await response.text());
      const projects = (await response.json()) as ProjectSummary[];
      this.projectSelectEl.empty();
      this.projectSelectEl.createEl("option", { text: "Select project", value: "" });
      for (const project of projects) {
        const option = this.projectSelectEl.createEl("option", {
          text: `${project.name} (${project.project_id})`,
          value: project.project_id,
        });
        option.selected = project.project_id === this.plugin.settings.projectId;
      }
      this.renderProjectList(projects);
      this.statusEl.setText(projects.length ? "Projects loaded." : "No projects yet.");
    } catch (error) {
      this.renderProjectList([]);
      this.statusEl.setText("Project list failed.");
      new Notice(`ProjectOS projects failed: ${String(error)}`);
    }
  }

  renderProjectList(projects: ProjectSummary[]): void {
    this.projectListEl.empty();
    if (!projects.length) {
      this.projectListEl.createDiv({
        cls: "projectos-empty",
        text: "No backend projects found.",
      });
      return;
    }

    for (const project of projects) {
      const item = this.projectListEl.createEl("button", { cls: "projectos-project-item" });
      item.toggleClass("is-selected", project.project_id === this.plugin.settings.projectId);
      const main = item.createDiv({ cls: "projectos-project-main" });
      main.createEl("strong", { text: project.name });
      if (project.description) main.createEl("span", { text: project.description });
      const meta = item.createDiv({ cls: "projectos-project-meta" });
      meta.createEl("span", { text: project.status ?? "unknown" });
      meta.createEl("code", { text: project.project_id });
      item.onclick = () => this.selectProject(project.project_id);
    }
  }

  async selectProject(projectId: string): Promise<void> {
    if (!projectId) return;
    this.projectSelectEl.value = projectId;
    const selected = this.projectSelectEl.selectedOptions[0];
    const match = selected?.text.match(/^(.*) \([^)]+\)$/);
    this.plugin.settings.projectId = projectId;
    this.plugin.settings.projectName = match?.[1] ?? projectId;
    await this.plugin.saveSettings();
    this.statusEl.setText(`Selected ${this.plugin.settings.projectName}.`);
    await this.refreshProjects();
  }

  async createProject(): Promise<void> {
    const name = this.projectNameInputEl.value.trim() || "Obsidian Project";
    this.statusEl.setText("Creating project...");
    try {
      const response = await fetch(this.plugin.apiUrl("/api/projects"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          description: "Created from Obsidian",
        }),
      });
      if (!response.ok) throw new Error(await response.text());
      const project = (await response.json()) as ProjectSummary;
      this.plugin.settings.projectId = project.project_id;
      this.plugin.settings.projectName = project.name;
      await this.plugin.saveSettings();
      await this.refreshProjects();
      this.statusEl.setText(`Created ${project.name}.`);
      new Notice(`ProjectOS project created: ${project.name}`);
    } catch (error) {
      this.statusEl.setText("Project create failed.");
      new Notice(`ProjectOS create failed: ${String(error)}`);
    }
  }

  async syncVault(): Promise<void> {
    const projectId = this.requireProjectId();
    if (!projectId) return;
    this.statusEl.setText("Syncing...");
    try {
      const response = await fetch(this.plugin.apiUrl(`/api/projects/${projectId}/vault/export`));
      if (!response.ok) throw new Error(await response.text());
      const payload = (await response.json()) as VaultPayload;
      const count = await writePayloadToVault(
        this.app,
        payload,
        this.targetFolderForCurrentProject(),
      );
      this.statusEl.setText(`Synced ${count} notes.`);
      new Notice(`ProjectOS synced ${count} notes.`);
    } catch (error) {
      this.statusEl.setText("Sync failed.");
      new Notice(`ProjectOS sync failed: ${String(error)}`);
    }
  }

  async uploadAndBuild(files: FileList | null): Promise<void> {
    const projectId = this.requireProjectId();
    if (!projectId || !files || files.length === 0) return;
    this.statusEl.setText("Uploading...");
    try {
      const form = new FormData();
      Array.from(files).forEach((file) => form.append("files", file));
      form.append("file_type", "note");
      const upload = await fetch(this.plugin.apiUrl(`/api/projects/${projectId}/files`), {
        method: "POST",
        body: form,
      });
      if (!upload.ok) throw new Error(await upload.text());

      const build = await fetch(this.plugin.apiUrl(`/api/projects/${projectId}/graph`), {
        method: "POST",
      });
      if (!build.ok) throw new Error(await build.text());
      const task = await build.json();
      this.statusEl.setText("Build started.");
      this.watchTask(task.task_id);
    } catch (error) {
      this.statusEl.setText("Upload/build failed.");
      new Notice(`ProjectOS build failed: ${String(error)}`);
    }
  }

  watchTask(taskId: string, onCompleted?: () => void): void {
    const events = new EventSource(this.plugin.apiUrl(`/api/tasks/${taskId}/stream`));
    events.onmessage = (event) => {
      const data = JSON.parse(event.data);
      this.statusEl.setText(`${data.progress ?? 0}% ${data.message ?? ""}`);
      if (data.status === "completed" || data.status === "failed") {
        events.close();
        if (data.status === "completed" && onCompleted) onCompleted();
      }
    };
    events.onerror = () => {
      events.close();
      this.statusEl.setText("Task stream disconnected.");
    };
  }

  async runAnalysis(): Promise<void> {
    const projectId = this.requireProjectId();
    if (!projectId) return;
    this.statusEl.setText("Starting analysis...");
    try {
      const response = await fetch(this.plugin.apiUrl(`/api/projects/${projectId}/analysis`), {
        method: "POST",
      });
      if (!response.ok) throw new Error(await response.text());
      const task = await response.json();
      this.watchTask(task.task_id, () => this.loadAnalysis());
    } catch (error) {
      this.statusEl.setText("Analysis failed.");
      new Notice(`ProjectOS analysis failed: ${String(error)}`);
    }
  }

  async loadAnalysis(): Promise<void> {
    const projectId = this.requireProjectId();
    if (!projectId) return;
    this.statusEl.setText("Loading analysis...");
    try {
      const response = await fetch(this.plugin.apiUrl(`/api/projects/${projectId}/analysis`));
      if (!response.ok) throw new Error(await response.text());
      const result = await response.json();
      this.renderAnalysisResult(result);
      this.statusEl.setText("Analysis loaded.");
    } catch (error) {
      this.statusEl.setText("Analysis unavailable.");
      new Notice(`ProjectOS analysis unavailable: ${String(error)}`);
    }
  }

  renderAnalysisResult(result: {
    summary?: string;
    generated_at?: string;
    issues?: Array<{ severity?: string; category?: string; description?: string; suggestion?: string }>;
    improved_draft?: string;
  }): void {
    this.analysisEl.empty();
    const summary = this.analysisEl.createDiv({ cls: "projectos-summary" });
    summary.createEl("div", { cls: "projectos-summary-title", text: "Summary" });
    summary.createEl("p", { text: result.summary || "No summary." });
    if (result.generated_at) {
      summary.createEl("span", {
        cls: "projectos-meta",
        text: new Date(result.generated_at).toLocaleString(),
      });
    }

    const issues = result.issues ?? [];
    const list = this.analysisEl.createDiv({ cls: "projectos-issues" });
    list.createEl("div", { cls: "projectos-summary-title", text: "Improvement points" });
    if (!issues.length) {
      list.createEl("p", { cls: "projectos-muted", text: "No issues found." });
    }
    for (const issue of issues) {
      const item = list.createDiv({ cls: "projectos-issue" });
      item.createEl("span", {
        cls: `projectos-severity projectos-severity-${issue.severity ?? "medium"}`,
        text: issue.severity ?? "medium",
      });
      item.createEl("strong", { text: issue.category ?? "Issue" });
      item.createEl("p", { text: issue.description ?? "" });
      item.createEl("div", { cls: "projectos-suggestion", text: issue.suggestion ?? "" });
    }

    if (result.improved_draft) {
      this.analysisEl.createEl("div", { cls: "projectos-summary-title", text: "Improved draft" });
      this.analysisEl.createEl("pre", {
        cls: "projectos-draft",
        text: result.improved_draft,
      });
    }
  }

  async ask(question: string): Promise<void> {
    const projectId = this.requireProjectId();
    if (!projectId || !question.trim()) return;
    this.answerEl.empty();
    this.statusEl.setText("Asking...");
    try {
      const response = await fetch(this.plugin.apiUrl(`/api/projects/${projectId}/chat`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      if (!response.ok || !response.body) throw new Error(await response.text());
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";
        for (const event of events) {
          const line = event.split("\n").find((part) => part.startsWith("data: "));
          if (!line) continue;
          const data = JSON.parse(line.slice(6));
          if (data.token) this.answerEl.appendText(data.token);
        }
      }
      this.statusEl.setText("Done.");
    } catch (error) {
      this.statusEl.setText("Query failed.");
      new Notice(`ProjectOS query failed: ${String(error)}`);
    }
  }
}
