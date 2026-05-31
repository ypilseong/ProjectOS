export interface BackendSettings {
  llm_backend: string;
  graph_build_mode: string;
  graph_extraction_backend: string;
  claude_code_model: string;
  chunk_size: number;
  chunk_overlap: number;
}

export const DEFAULT_BACKEND_SETTINGS: BackendSettings = {
  llm_backend: "local",
  graph_build_mode: "chunk",
  graph_extraction_backend: "local",
  claude_code_model: "",
  chunk_size: 500,
  chunk_overlap: 50,
};

export const RUNTIME_PRESETS: Array<{
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

export function mergeBackendSettings(settings: Partial<BackendSettings>): BackendSettings {
  return { ...DEFAULT_BACKEND_SETTINGS, ...settings };
}

export function parsePositiveInt(value: string, fallback: number): number {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

export function matchRuntimePreset(settings: BackendSettings): string | null {
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
