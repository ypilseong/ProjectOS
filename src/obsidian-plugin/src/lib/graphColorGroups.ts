export const GRAPH_COLOR_GROUPS = [
  ["person", 0x4895ef],
  ["project", 0x2a9d8f],
  ["skill", 0xf4a261],
  ["organization", 0x9b5de5],
  ["publication", 0xe76f51],
  ["role", 0x00b4d8],
  ["achievement", 0xf9c74f],
  ["event", 0x90be6d],
  ["institution", 0xf72585],
  ["category", 0x8d99ae],
] as const;

export interface ColorGroup {
  query: string;
  color: { a: number; rgb: number };
}

export function buildColorGroups(existing: unknown): ColorGroup[] {
  const existingGroups = Array.isArray(existing) ? existing : [];
  const managedQueries = new Set(GRAPH_COLOR_GROUPS.map(([tag]) => `tag:#${tag}`));
  return [
    ...existingGroups.filter((group) => {
      if (!group || typeof group !== "object") return true;
      const query = (group as { query?: unknown }).query;
      return typeof query !== "string" || !managedQueries.has(query);
    }),
    ...GRAPH_COLOR_GROUPS.map(([tag, rgb]) => ({
      query: `tag:#${tag}`,
      color: { a: 1, rgb },
    })),
  ];
}
