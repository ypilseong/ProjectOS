import { describe, expect, it } from 'vitest'
import { extractMergeCandidates } from './mergeCandidates.js'

describe('extractMergeCandidates', () => {
  it('returns [] when graph data or candidates are missing', () => {
    expect(extractMergeCandidates(null)).toEqual([])
    expect(extractMergeCandidates({})).toEqual([])
    expect(extractMergeCandidates({ graph: {} })).toEqual([])
    expect(extractMergeCandidates({ graph: { merge_candidates: null } })).toEqual([])
  })

  it('returns the candidate list when present', () => {
    const gd = { graph: { merge_candidates: [{ keep_id: 'a', confidence: 0.8 }] } }
    expect(extractMergeCandidates(gd)).toHaveLength(1)
  })

  it('sorts by confidence descending', () => {
    const gd = {
      graph: {
        merge_candidates: [
          { keep_id: 'a', confidence: 0.7 },
          { keep_id: 'b', confidence: 0.9 },
          { keep_id: 'c', confidence: 0.8 },
        ],
      },
    }
    expect(extractMergeCandidates(gd).map((c) => c.keep_id)).toEqual(['b', 'c', 'a'])
  })

  it('does not mutate the input array', () => {
    const list = [
      { keep_id: 'a', confidence: 0.7 },
      { keep_id: 'b', confidence: 0.9 },
    ]
    const gd = { graph: { merge_candidates: list } }
    extractMergeCandidates(gd)
    expect(list.map((c) => c.keep_id)).toEqual(['a', 'b'])
  })
})
