import assert from "node:assert/strict";
import { test } from "node:test";

import {
  DEFAULT_BACKEND_SETTINGS,
  RUNTIME_PRESETS,
  mergeBackendSettings,
  matchRuntimePreset,
  parsePositiveInt,
} from "../src/lib/runtime";

test("parsePositiveInt returns parsed value or fallback", () => {
  assert.equal(parsePositiveInt("1800", 500), 1800);
  assert.equal(parsePositiveInt("abc", 500), 500);
  assert.equal(parsePositiveInt("-5", 500), 500);
});

test("mergeBackendSettings fills defaults", () => {
  const merged = mergeBackendSettings({ llm_backend: "claude_code" });
  assert.equal(merged.llm_backend, "claude_code");
  assert.equal(merged.chunk_size, DEFAULT_BACKEND_SETTINGS.chunk_size);
});

test("matchRuntimePreset finds the local preset", () => {
  const settings = mergeBackendSettings(
    RUNTIME_PRESETS.find((p) => p.id === "local")!.settings,
  );
  assert.equal(matchRuntimePreset(settings), "local");
});

test("matchRuntimePreset returns null for custom settings", () => {
  const settings = mergeBackendSettings({
    llm_backend: "local",
    graph_build_mode: "claude_task",
    graph_extraction_backend: "local",
  });
  assert.equal(matchRuntimePreset(settings), null);
});
