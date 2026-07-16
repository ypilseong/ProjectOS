import {
  App,
  ItemView,
  Plugin,
  PluginSettingTab,
  Setting,
  WorkspaceLeaf,
} from "obsidian";
import { mount, unmount } from "svelte";

import App_ from "./App.svelte";
import { ApiClient } from "./api/client";
import { AppStore } from "./store/appStore.svelte";

const VIEW_TYPE_PROJECTOS = "projectos-vault-sync-view";

interface ProjectOSSettings {
  baseUrl: string;
  projectId: string;
  projectName: string;
  targetFolder: string;
}

const DEFAULT_SETTINGS: ProjectOSSettings = {
  baseUrl: "http://localhost:14006",
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
        .setPlaceholder("http://localhost:14006")
        .setValue(this.plugin.settings.baseUrl)
        .onChange(async (value) => {
          this.plugin.settings.baseUrl = value.trim() || DEFAULT_SETTINGS.baseUrl;
          await this.plugin.saveSettings();
        }),
    );

    new Setting(containerEl)
      .setName("Project ID")
      .setDesc("Auto-filled when a project is selected in the ProjectOS panel.")
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
  }
}
