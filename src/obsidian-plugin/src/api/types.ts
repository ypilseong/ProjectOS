export interface ProjectSummary {
  project_id: string;
  name: string;
  description?: string;
  status?: string;
}

export interface TaskUpdate {
  progress?: number;
  message?: string;
  status?: string;
}

export interface AnalysisResult {
  summary?: string;
  generated_at?: string;
  issues?: Array<{ severity?: string; category?: string; description?: string; suggestion?: string }>;
  improved_draft?: string;
}

export interface SimulationResult {
  personas?: Array<{ agent_id?: string; name?: string; role?: string; goals?: string[]; knowledge?: string[] }>;
  environment?: { objective?: string; rules?: string[]; constraints?: string[] };
  timeline?: Array<{ round?: number; agent_id?: string; observation?: string; proposal?: string }>;
  applied_graph_changes?: { nodes_added?: number; edges_added?: number };
  cv_improvements?: { summary?: string; improved_draft?: string; bullets?: string[] };
  report?: { title?: string; answer?: string; recommendations?: string[]; evidence?: string[] };
}
