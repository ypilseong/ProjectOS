import assert from "node:assert/strict";
import { test } from "node:test";

import { buildVaultSyncPlan, joinVaultPath, type VaultPayload } from "../vaultSync";

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
