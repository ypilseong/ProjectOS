import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildVaultSyncPlan,
  deletionTargetFolder,
  isSafeGeneratedProjectFolder,
  joinVaultPath,
  projectTargetFolder,
  type VaultPayload,
} from "../src/lib/vaultSync";

test("joinVaultPath trims slashes and skips empty parts", () => {
  assert.equal(joinVaultPath("/ProjectOS/", "Skills", "/Python.md"), "ProjectOS/Skills/Python.md");
  assert.equal(joinVaultPath("", "Career", "Yang.md"), "Career/Yang.md");
});

test("buildVaultSyncPlan maps payload into generated folder clears and writes", () => {
  const payload: VaultPayload = {
    notes: [
      { folder: "Career", filename: "Yang.md", content: "# Yang" },
      { folder: "Skills", filename: "Python.md", content: "# Python" },
    ],
    canvas: { filename: "_index.canvas", content: "{}" },
    index: { filename: "_index.md", content: "# Graph Index" },
    log_entry: "## 2026-05-30 graph build",
  };

  const plan = buildVaultSyncPlan(payload, "ProjectOS");

  assert.equal(plan.noteCount, 2);
  assert.ok(plan.clearFolders.includes("ProjectOS/Career"));
  assert.ok(plan.clearFolders.includes("ProjectOS/Skills"));
  assert.deepEqual(
    plan.writes.map((write) => write.path),
    [
      "ProjectOS/Career/Yang.md",
      "ProjectOS/Skills/Python.md",
      "ProjectOS/_index.canvas",
      "ProjectOS/_index.md",
      "ProjectOS/log.md",
    ],
  );
  assert.equal(plan.writes.at(-1)?.content, "# ProjectOS Log\n\n## 2026-05-30 graph build");
});

test("projectTargetFolder uses explicit folder or ProjectOS project name", () => {
  assert.equal(
    projectTargetFolder({ projectId: "p1", projectName: "KAIST CV", targetFolder: "" }),
    "ProjectOS/KAIST CV",
  );
  assert.equal(
    projectTargetFolder({ projectId: "p1", projectName: "KAIST CV", targetFolder: "Custom/Folder" }),
    "Custom/Folder",
  );
});

test("deletionTargetFolder only uses explicit folder for selected project", () => {
  const settings = { projectId: "selected", projectName: "Selected Project", targetFolder: "Custom/Folder" };

  assert.equal(deletionTargetFolder(settings, "selected", "Selected Project"), "Custom/Folder");
  assert.equal(deletionTargetFolder(settings, "other", "Other Project"), "ProjectOS/Other Project");
});

test("isSafeGeneratedProjectFolder rejects root and Obsidian config paths", () => {
  assert.equal(isSafeGeneratedProjectFolder("ProjectOS/KAIST CV"), true);
  assert.equal(isSafeGeneratedProjectFolder(""), false);
  assert.equal(isSafeGeneratedProjectFolder(".obsidian/plugins"), false);
  assert.equal(isSafeGeneratedProjectFolder("ProjectOS/../Other"), false);
});
