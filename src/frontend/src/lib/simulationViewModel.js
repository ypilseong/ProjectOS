export function buildSimulationViewModel(result) {
  const isV2 = result?.schema_version === '2.0'
  const personas = buildPersonas(result)
  const reportSections = buildReportSections(result)
  const debateRounds = buildDebateRounds(result, personas)
  const graphDeltaItems = buildGraphDeltaItems(result)
  const workflowSteps = buildWorkflowSteps(result, reportSections, debateRounds, graphDeltaItems)
  const evidenceRefs = buildEvidenceRefs(reportSections, debateRounds, graphDeltaItems, personas)

  return {
    isV2,
    title: result?.summary?.title || result?.report?.title || reportSections[0]?.title || 'Simulation Report',
    status: result?.status || (isV2 ? 'unknown' : 'legacy'),
    query: result?.query || '',
    summaryText: result?.summary?.text || result?.summary?.answer || result?.report?.answer || result?.environment?.objective || '',
    workflowSteps,
    reportSections,
    personas,
    debateRounds,
    graphDeltaItems,
    evidenceRefs,
    graphChanges: result?.applied_graph_changes || { nodes_added: 0, edges_added: 0 },
  }
}

export function buildSimulationOverlay(graphData, result, mode = 'highlight') {
  const deltaItems = buildGraphDeltaItems(result)
  const nodeIds = new Set()
  const linkIds = new Set()
  const nodesByName = new Map((graphData?.nodes || []).map(node => [nodeNameKey(node.type, node.name), node.id]))
  const nodesById = new Set((graphData?.nodes || []).map(node => node.id))
  const deltaNodes = []
  const deltaLinks = []

  for (const item of deltaItems) {
    if (item.type === 'node') {
      const id = item.nodeId || nodesByName.get(nodeNameKey(item.nodeType, item.nodeName)) || `${item.nodeType}:${item.nodeName}`
      nodeIds.add(id)
      if (!nodesById.has(id)) {
        deltaNodes.push({
          id,
          name: item.nodeName || item.label,
          type: item.nodeType || 'Simulation',
          description: item.statusReason || item.evidenceRefs.join(', '),
        })
      }
    } else if (item.type === 'edge') {
      const source = item.sourceId || nodesByName.get(nodeNameKey(item.sourceType, item.sourceName)) || item.sourceName
      const target = item.targetId || nodesByName.get(nodeNameKey(item.targetType, item.targetName)) || item.targetName
      if (source) nodeIds.add(source)
      if (target) nodeIds.add(target)
      const key = `${source}->${target}:${item.relation || ''}`
      linkIds.add(key)
      deltaLinks.push({
        id: key,
        source,
        target,
        relation: item.relation,
        confidence: item.confidence,
      })
    }
  }

  if (mode === 'delta') {
    const graphNodes = [...(graphData?.nodes || []).filter(node => nodeIds.has(node.id)), ...deltaNodes]
    const graphNodeIds = new Set(graphNodes.map(node => node.id))
    const existingLinks = (graphData?.links || graphData?.edges || []).filter(link => {
      const source = typeof link.source === 'object' ? link.source.id : link.source
      const target = typeof link.target === 'object' ? link.target.id : link.target
      return graphNodeIds.has(source) && graphNodeIds.has(target) &&
        (linkIds.has(link.id) || linkIds.has(`${source}->${target}:${link.relation || ''}`))
    })
    return {
      graphData: { nodes: graphNodes, links: [...existingLinks, ...deltaLinks] },
      highlightNodeIds: [...nodeIds],
      highlightLinkIds: [...linkIds],
    }
  }

  return {
    graphData,
    highlightNodeIds: [...nodeIds],
    highlightLinkIds: [...linkIds],
  }
}

function buildPersonas(result) {
  return (result?.personas || []).map((persona, index) => {
    const id = persona.persona_id || persona.agent_id || persona.id || `persona_${index + 1}`
    return {
      id,
      name: persona.name || id,
      role: persona.role || 'Reviewer',
      stance: persona.stance || '',
      focusAreas: nonEmptyStrings(persona.focus_areas || persona.goals),
      keyPoints: nonEmptyStrings(persona.key_points || persona.knowledge),
      sourceNodeIds: nonEmptyStrings(persona.source_node_ids || persona.source_nodes),
    }
  })
}

function buildReportSections(result) {
  const sections = (result?.report_sections || []).map((section, index) => ({
    id: section.id || section.section_id || `section_${index + 1}`,
    title: section.title || section.id || `Section ${index + 1}`,
    kind: section.kind || 'report',
    summary: section.summary || '',
    body: typeof section.body === 'string' ? section.body : section.content || section.text || '',
    items: nonEmptyStrings(section.items || section.recommendations || section.bullets),
    evidenceRefs: nonEmptyStrings(section.evidence_refs || section.evidence),
    uncertainties: nonEmptyStrings(section.uncertainties || section.open_questions),
  }))
  if (sections.length) return sections

  const fallback = []
  if (result?.report) {
    fallback.push({
      id: 'report',
      title: result.report.title || 'Simulation report',
      kind: 'executive_summary',
      summary: result.report.answer || '',
      body: result.report.answer || '',
      items: nonEmptyStrings(result.report.recommendations),
      evidenceRefs: nonEmptyStrings(result.report.evidence),
      uncertainties: [],
    })
  }
  if (result?.cv_improvements) {
    fallback.push({
      id: 'cv_improvements',
      title: 'CV improvements',
      kind: 'cv_improvements',
      summary: result.cv_improvements.summary || '',
      body: result.cv_improvements.improved_draft || '',
      items: nonEmptyStrings(result.cv_improvements.bullets),
      evidenceRefs: [],
      uncertainties: [],
    })
  }
  return fallback
}

function buildDebateRounds(result, personas) {
  const turns = result?.debate?.turns?.length
    ? result.debate.turns.map((turn, index) => {
      const speakerId = turn.speaker_id || turn.agent_id || turn.persona_id || ''
      return {
        id: turn.id || turn.turn_id || `turn_${index + 1}`,
        round: turn.round || index + 1,
        speakerId,
        speakerName: personaName(personas, speakerId),
        claim: turn.claim || turn.observation || turn.message || '',
        proposal: turn.proposal || turn.recommendation || '',
        evidenceRefs: nonEmptyStrings(turn.evidence_refs || turn.evidence),
      }
    })
    : (result?.timeline || []).map((event, index) => ({
      id: `legacy_turn_${index + 1}`,
      round: event.round || 0,
      speakerId: event.agent_id || '',
      speakerName: personaName(personas, event.agent_id || ''),
      claim: event.observation || '',
      proposal: event.proposal || '',
      evidenceRefs: [],
    }))

  const groups = new Map()
  for (const turn of turns) {
    groups.set(turn.round, [...(groups.get(turn.round) || []), turn])
  }
  return [...groups.entries()].sort((a, b) => a[0] - b[0]).map(([round, groupedTurns]) => ({
    round,
    turns: groupedTurns,
  }))
}

function buildGraphDeltaItems(result) {
  const v2 = result?.graph_delta
  const v2Items = [
    ...(v2?.items || []),
    ...(v2?.nodes || []).map(item => ({ ...item, item_type: 'node' })),
    ...(v2?.edges || []).map(item => ({ ...item, item_type: 'edge' })),
  ]
  if (v2Items.length) {
    return v2Items.map((item, index) => normalizeDeltaItem(item, index))
  }

  const nodes = (result?.graph_enhancements?.nodes || []).map((node, index) => normalizeDeltaItem({
    ...node,
    item_type: 'node',
    operation: 'add',
    status: 'proposed',
  }, index))
  const edges = (result?.graph_enhancements?.edges || []).map((edge, index) => normalizeDeltaItem({
    ...edge,
    item_type: 'edge',
    operation: 'add',
    status: 'proposed',
  }, nodes.length + index))
  return [...nodes, ...edges]
}

function normalizeDeltaItem(item, index) {
  const isEdge = item.item_type === 'edge' || item.type === 'edge' || item.source_name || item.target_name
  if (isEdge) {
    const sourceName = item.source_name || item.source_label || item.source || ''
    const targetName = item.target_name || item.target_label || item.target || ''
    return {
      id: item.id || item.delta_id || `delta_${index + 1}`,
      type: 'edge',
      operation: item.operation || item.op || 'update',
      label: item.label || `${sourceName} → ${targetName}`,
      sourceId: item.source_id,
      targetId: item.target_id,
      sourceType: item.source_type,
      targetType: item.target_type,
      sourceName,
      targetName,
      relation: item.relation || '',
      confidence: numericOrNull(item.confidence),
      status: item.status || 'proposed',
      statusReason: item.status_reason || item.reason || '',
      evidenceRefs: nonEmptyStrings(item.evidence_refs || item.evidence),
    }
  }
  const nodeType = item.node_type || item.type || item.item_type || 'Node'
  const nodeName = item.name || item.node_name || item.label || `Node ${index + 1}`
  return {
    id: item.id || item.delta_id || `delta_${index + 1}`,
    type: 'node',
    operation: item.operation || item.op || 'update',
    label: item.label || `${nodeType}: ${nodeName}`,
    nodeId: item.node_id,
    nodeType,
    nodeName,
    relation: '',
    confidence: numericOrNull(item.confidence),
    status: item.status || 'proposed',
    statusReason: item.status_reason || item.reason || item.description || '',
    evidenceRefs: nonEmptyStrings(item.evidence_refs || item.evidence),
  }
}

function buildWorkflowSteps(result, sections, debateRounds, deltas) {
  if (result?.workflow_steps?.length) {
    return result.workflow_steps.map((step, index) => ({
      id: step.id || step.step_id || `step_${index + 1}`,
      label: step.label || titleCase(step.id || step.step_id || `step ${index + 1}`),
      status: step.status || 'waiting',
      summary: step.summary || step.message || '',
    }))
  }
  return [
    { id: 'context', label: 'Context', status: 'completed', summary: result?.query || 'Project graph loaded' },
    { id: 'personas', label: 'Personas', status: result?.personas?.length ? 'completed' : 'waiting', summary: `${result?.personas?.length || 0} agents` },
    { id: 'debate', label: 'Debate', status: debateRounds.length ? 'completed' : 'waiting', summary: `${debateRounds.length} rounds` },
    { id: 'delta', label: 'Graph Delta', status: deltas.length ? 'completed' : 'waiting', summary: `${deltas.length} items` },
    { id: 'report', label: 'Report', status: sections.length ? 'completed' : 'waiting', summary: `${sections.length} sections` },
  ]
}

function buildEvidenceRefs(sections, debateRounds, deltas, personas) {
  const refs = new Map()
  const add = (id, source) => {
    if (!id || refs.has(id)) return
    refs.set(id, { id, source })
  }
  sections.forEach(section => section.evidenceRefs.forEach(ref => add(ref, section.title)))
  debateRounds.forEach(group => group.turns.forEach(turn => turn.evidenceRefs.forEach(ref => add(ref, turn.speakerName))))
  deltas.forEach(delta => delta.evidenceRefs.forEach(ref => add(ref, delta.label)))
  personas.forEach(persona => persona.sourceNodeIds.forEach(ref => add(ref, persona.name)))
  return [...refs.values()]
}

function personaName(personas, id) {
  return personas.find(persona => persona.id === id)?.name || id || 'agent'
}

function nonEmptyStrings(value) {
  if (!value) return []
  if (Array.isArray(value)) return value.map(item => String(item).trim()).filter(Boolean)
  if (typeof value === 'string' && value.trim()) return [value.trim()]
  return []
}

function numericOrNull(value) {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function titleCase(value) {
  return String(value).replace(/[_-]+/g, ' ').replace(/\b\w/g, char => char.toUpperCase())
}

function nodeNameKey(type, name) {
  return `${type || ''}:${String(name || '').toLowerCase().trim()}`
}
