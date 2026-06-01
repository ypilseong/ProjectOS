import { App, TFile } from "obsidian";

import {
  GENERATED_FOLDERS,
  buildVaultSyncPlan,
  isSafeGeneratedProjectFolder,
  joinVaultPath,
  type VaultPayload,
} from "./vaultSync";
import { buildColorGroups, GRAPH_COLOR_GROUPS } from "./graphColorGroups";

export { GRAPH_COLOR_GROUPS, buildColorGroups } from "./graphColorGroups";

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

async function ensureGraphColorGroups(app: App): Promise<void> {
  const path = ".obsidian/graph.json";
  let config: Record<string, unknown> = {};
  if (await app.vault.adapter.exists(path)) {
    try {
      config = JSON.parse(await app.vault.adapter.read(path)) as Record<string, unknown>;
    } catch {
      config = {};
    }
  }
  config.colorGroups = buildColorGroups(config.colorGroups);
  await writeText(app, path, JSON.stringify(config, null, 2));
}

async function clearGenerated(app: App, targetFolder: string): Promise<void> {
  for (const folder of GENERATED_FOLDERS) {
    const path = joinVaultPath(targetFolder, folder);
    if (await app.vault.adapter.exists(path)) {
      await app.vault.adapter.rmdir(path, true);
    }
  }
}

export async function deleteProjectFolderFromVault(app: App, targetFolder: string): Promise<boolean> {
  const path = joinVaultPath(targetFolder);
  if (!isSafeGeneratedProjectFolder(path)) {
    throw new Error(`Refusing to delete unsafe ProjectOS folder: ${targetFolder}`);
  }
  if (!(await app.vault.adapter.exists(path))) return false;
  await app.vault.adapter.rmdir(path, true);
  return true;
}

export async function writePayloadToVault(
  app: App,
  payload: VaultPayload,
  targetFolder: string,
): Promise<number> {
  const plan = buildVaultSyncPlan(payload, targetFolder);
  await clearGenerated(app, targetFolder);
  for (const write of plan.writes) {
    await writeText(app, write.path, write.content);
  }
  await ensureGraphColorGroups(app);
  return plan.noteCount;
}
