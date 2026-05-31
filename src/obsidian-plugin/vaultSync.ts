export const GENERATED_FOLDERS = [
  "Career",
  "Projects",
  "Skills",
  "Organizations",
  "Publications",
  "Roles",
  "Achievements",
  "Events",
  "Institutions",
  "Misc",
];

export interface VaultNote {
  folder: string;
  filename: string;
  content: string;
}

export interface VaultFile {
  filename: string;
  content: string;
}

export interface VaultPayload {
  notes: VaultNote[];
  canvas: VaultFile;
  index: VaultFile;
  log_entry: string;
}

export interface VaultSyncPlan {
  clearFolders: string[];
  writes: Array<{ path: string; content: string }>;
  noteCount: number;
}

export function joinVaultPath(...parts: string[]): string {
  return parts
    .map((part) => part.trim().replace(/^\/+|\/+$/g, ""))
    .filter(Boolean)
    .join("/");
}

export function buildVaultSyncPlan(
  payload: VaultPayload,
  targetFolder: string,
): VaultSyncPlan {
  const clearFolders = GENERATED_FOLDERS.map((folder) => joinVaultPath(targetFolder, folder));
  const writes = payload.notes.map((note) => ({
    path: joinVaultPath(targetFolder, note.folder, note.filename),
    content: note.content,
  }));

  writes.push(
    {
      path: joinVaultPath(targetFolder, payload.canvas.filename),
      content: payload.canvas.content,
    },
    {
      path: joinVaultPath(targetFolder, payload.index.filename),
      content: payload.index.content,
    },
    {
      path: joinVaultPath(targetFolder, "log.md"),
      content: `# ProjectOS Log\n\n${payload.log_entry}`,
    },
  );

  return {
    clearFolders,
    writes,
    noteCount: payload.notes.length,
  };
}
