import { describe, expect, it } from 'vitest'
import {
  buildSimulationViewModel,
  indexResolvedEvidence,
  normalizeResolvedEvidence,
  resolveEvidenceRefList,
} from './simulationViewModel.js'

const samplePayload = {
  kind: 'simulation_evidence',
  refs: [
    {
      ref: 'chunk:cv.pdf#c1',
      kind: 'chunk',
      resolved: true,
      source_file: 'cv.pdf',
      page_num: 2,
      text: 'Yang uses Python daily.',
    },
    {
      ref: 'node:Skill:Python',
      kind: 'node',
      resolved: true,
      name: 'Python',
      type: 'Skill',
      evidence: [
        { source_file: 'cv.pdf', chunk_id: 'c1', page_num: 2, quote: 'uses Python', confidence: 0.9, directness: 'direct' },
      ],
    },
  ],
  unresolved_refs: ['chunk:nope#missing'],
}

describe('indexResolvedEvidence', () => {
  it('builds a lookup keyed by ref id', () => {
    const { items } = normalizeResolvedEvidence(samplePayload)
    const index = indexResolvedEvidence(items)
    expect(index['node:Skill:Python'].title).toBe('Python')
    expect(index['chunk:cv.pdf#c1'].quote).toBe('Yang uses Python daily.')
  })

  it('returns an empty object for no items', () => {
    expect(indexResolvedEvidence([])).toEqual({})
    expect(indexResolvedEvidence(undefined)).toEqual({})
  })
})

describe('resolveEvidenceRefList', () => {
  it('maps ref ids to resolved items in order', () => {
    const { items } = normalizeResolvedEvidence(samplePayload)
    const index = indexResolvedEvidence(items)
    const result = resolveEvidenceRefList(['node:Skill:Python', 'chunk:cv.pdf#c1'], index)
    expect(result.map(item => item.id)).toEqual(['node:Skill:Python', 'chunk:cv.pdf#c1'])
    expect(result[0].resolved).toBe(true)
  })

  it('emits an unresolved placeholder for unknown ids', () => {
    const index = indexResolvedEvidence([])
    const [item] = resolveEvidenceRefList(['edge:A->B:REL'], index)
    expect(item).toMatchObject({
      id: 'edge:A->B:REL',
      resolved: false,
      title: 'edge:A->B:REL',
      anchors: [],
      isWeak: false,
    })
  })

  it('ignores empty ids', () => {
    expect(resolveEvidenceRefList(['', null, undefined], {})).toEqual([])
    expect(resolveEvidenceRefList(undefined, {})).toEqual([])
  })
})

describe('buildSimulationViewModel — debate turn evidence', () => {
  const result = {
    debate: {
      turns: [
        {
          id: 'turn_1',
          round: 1,
          speaker_id: 'p1',
          claim: 'Python is the core skill.',
          proposal: 'Lead with backend work.',
          evidence_refs: ['node:Skill:Python', 'chunk:cv.pdf#c1'],
        },
      ],
    },
    personas: [{ id: 'p1', name: 'Backend Advocate', role: 'engineer' }],
  }

  it('exposes turn evidence refs at vm.debateRounds[].turns[].evidenceRefs', () => {
    const vm = buildSimulationViewModel(result)
    const turn = vm.debateRounds[0].turns[0]
    expect(turn.evidenceRefs).toEqual(['node:Skill:Python', 'chunk:cv.pdf#c1'])
  })

  it('folds turn evidence refs into the global vm.evidenceRefs', () => {
    const vm = buildSimulationViewModel(result)
    const ids = vm.evidenceRefs.map(ref => ref.id)
    expect(ids).toContain('node:Skill:Python')
    expect(ids).toContain('chunk:cv.pdf#c1')
  })
})
