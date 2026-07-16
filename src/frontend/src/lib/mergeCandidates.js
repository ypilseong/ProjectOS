export function extractMergeCandidates(graphData) {
  const list = graphData?.graph?.merge_candidates
  if (!Array.isArray(list)) return []
  return [...list].sort((a, b) => (b.confidence ?? 0) - (a.confidence ?? 0))
}
