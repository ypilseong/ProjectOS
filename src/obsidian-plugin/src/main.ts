import {
  App,
  DropdownComponent,
  ItemView,
  Notice,
  Plugin,
  PluginSettingTab,
  Setting,
  TextComponent,
  WorkspaceLeaf,
} from "obsidian";
import { mount, unmount } from "svelte";

import App_ from "./App.svelte";
import { ApiClient } from "./api/client";
import { AppStore } from "./store/appStore.svelte";
import {
  BackendSettings,
  DEFAULT_BACKEND_SETTINGS,
  RUNTIME_PRESETS,
  mergeBackendSettings,
  parsePositiveInt,
} from "./lib/runtime";
import { deleteProjectFolderFromVault } from "./lib/graphColors";

const VIEW_TYPE_PROJECTOS = "projectos-vault-sync-view";

interface ProjectOSSettings {
  baseUrl: string;
  projectId: string;
  projectName: string;
  targetFolder: string;
}

const DEFAULT_SETTINGS: ProjectOSSettings = {
  baseUrl: "http://localhost:8002",
  projectId: "",
  projectName: "",
  targetFolder: "",
};

export default class ProjectOSPlugin extends Plugin {
  settings: ProjectOSSettings = DEFAULT_SETTINGS;
  client = new ApiClient(() => this.settings.baseUrl);

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

  async getBackendSettings(): Promise<BackendSettings> {
    return this.client.getBackendSettings();
  }

  async setBackendSettings(settings: BackendSettings): Promise<BackendSettings> {
    return this.client.setBackendSettings(settings);
  }

  async deleteProjectFolder(targetFolder: string): Promise<boolean> {
    return deleteProjectFolderFromVault(this.app, targetFolder);
  }
}

class ProjectOSView extends ItemView {
  plugin: ProjectOSPlugin;
  private component: ReturnType<typeof mount> | null = null;
  private rootEl: HTMLElement | null = null;

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
    const root = (this.containerEl.children[1] ?? this.containerEl) as HTMLElement;
    this.rootEl = root;
    root.empty();
    root.addClass("projectos-view-root");

    try {
      const store = new AppStore(this.plugin.client, this.plugin);
      this.component = mount(App_, { target: root, props: { store, app: this.app } });
      await store.loadBackendSettings();
      await store.refreshProjects();
    } catch (error) {
      console.error("ProjectOS view failed to open", error);
      this.renderOpenError(root, error);
    }
  }

  async onClose(): Promise<void> {
    if (this.component) {
      unmount(this.component);
      this.component = null;
    }
  }

  private renderOpenError(root: HTMLElement, error: unknown): void {
    root.empty();
    const panel = root.createDiv({ cls: "pos-panel pos-fallback" });
    panel.createEl("h2", { text: "ProjectOS" });
    panel.createEl("p", {
      cls: "pos-error-title",
      text: "ProjectOS plugin view failed to render.",
    });
    panel.createEl("p", {
      cls: "pos-muted",
      text: "Open the Obsidian developer console for the full stack trace, or reload this view after updating the plugin files.",
    });

    const message = error instanceof Error ? error.stack ?? error.message : String(error);
    panel.createEl("pre", { cls: "pos-error-box", text: message });

    const actions = panel.createDiv({ cls: "pos-actions" });
    const retry = actions.createEl("button", { cls: "pos-btn pos-btn-primary", text: "Retry" });
    retry.onclick = () => {
      this.onOpen().catch((retryError) => {
        console.error("ProjectOS view retry failed", retryError);
        if (this.rootEl) this.renderOpenError(this.rootEl, retryError);
      });
    };
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

    new Setting(containerEl).setName("Backend base URL").addText((text) =>
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

    new Setting(containerEl).setName("Target folder").addText((text) =>
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

    new Setting(section).setName("LLM backend").addDropdown((dropdown) => {
      llmBackend = dropdown.addOption("local", "Local LLM").addOption("claude_code", "Claude Code");
    });

    new Setting(section).setName("Graph build mode").addDropdown((dropdown) => {
      graphMode = dropdown.addOption("chunk", "Chunk extraction").addOption("claude_task", "Claude task mode");
    });

    new Setting(section).setName("Chunk extraction backend").addDropdown((dropdown) => {
      graphBackend = dropdown.addOption("local", "Local LLM").addOption("claude_code", "Claude Code");
    });

    new Setting(section).setName("Claude Code model").addText((text) => {
      claudeModel = text.setPlaceholder("claude-haiku-4-5");
    });

    new Setting(section).setName("Chunk size").addText((text) => {
      chunkSize = text.setPlaceholder("1800");
    });

    new Setting(section).setName("Chunk overlap").addText((text) => {
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
