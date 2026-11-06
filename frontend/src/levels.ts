// The alignment levels (SPEC §2, "Levels: sentences, turns, paragraphs"): a unit at a level is the run of beads up to
// and including a bead whose end flag for that level is true. Units are derived, never stored.
import type { BookBead, BookSegment } from '@/api/client'

export type Level = 'sentence' | 'turn' | 'paragraph'

/** Review ranks, coarse to fine; a bead's `review_level` null is rank 0 (unreviewed). */
export const RANK: Record<Level, number> = { paragraph: 1, turn: 2, sentence: 3 }

/** In the order `L` cycles through them. */
export const LEVELS: readonly Level[] = ['sentence', 'turn', 'paragraph']

export const LEVEL_LABELS: Record<Level, string> = { sentence: 'Sentences', turn: 'Turns', paragraph: 'Paragraphs' }

/** What a row is called at a level: a "bead" at sentence level. */
export function unitNoun(level: Level, n = 1): string {
  const noun = level === 'sentence' ? 'bead' : level
  return n === 1 ? noun : `${noun}s`
}

// Mirrors `is_speech` and `SPEECH_OPENERS` in tradurre/domain/levels.py: the two must stay in sync.
const SPEECH_OPENERS = '—–-«'

// Python's `str.isspace` set, not JS's `trim` set (they differ on U+FEFF, U+001C-U+001F and U+0085).
const LEADING_SPACE = /^[\t\n\v\f\r\x1c-\x1f \x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+/

/** Whether the text is empty or only whitespace (Python's `not text.strip()`). */
export function isBlank(text: string): boolean {
  return text.replace(LEADING_SPACE, '').length === 0
}

/** Whether the text opens with a dialogue mark (its first non-whitespace character). */
export function isSpeech(text: string): boolean {
  const stripped = text.replace(LEADING_SPACE, '')
  return stripped.length > 0 && SPEECH_OPENERS.includes(stripped[0]!)
}

export function beadRank(bead: BookBead): number {
  return bead.review_level === null ? 0 : RANK[bead.review_level]
}

export interface Unit {
  /** The first bead's id. */
  id: number
  level: Level
  beads: BookBead[]
  /** The beads' segments concatenated, in order. */
  source: BookSegment[]
  target: BookSegment[]
  /** The lowest confidence of its beads. */
  confidence: number
  /** Every bead was reviewed at this level or a finer one. */
  reviewed: boolean
}

function makeUnit(level: Level, beads: BookBead[]): Unit {
  const one = beads.length === 1
  return {
    id: beads[0]!.id,
    level,
    beads,
    source: one ? beads[0]!.source : beads.flatMap((b) => b.source),
    target: one ? beads[0]!.target : beads.flatMap((b) => b.target),
    confidence: Math.min(...beads.map((b) => b.confidence)),
    reviewed: beads.every((b) => beadRank(b) >= RANK[level]),
  }
}

function sameBeads(a: BookBead[], b: BookBead[]): boolean {
  return a.length === b.length && a.every((bead, i) => bead === b[i])
}

/**
 * The book's units at a level. A unit whose beads are the very same objects as in `previous` (the units last built at
 * this level, by first bead id) is reused as it was, so `reconcile`'s reuse of unchanged beads carries over to rows.
 */
export function buildUnits(beads: BookBead[], level: Level, previous?: ReadonlyMap<number, Unit>): Unit[] {
  const units: Unit[] = []
  let run: BookBead[] = []
  const flush = () => {
    const old = previous?.get(run[0]!.id)
    units.push(old && old.level === level && sameBeads(old.beads, run) ? old : makeUnit(level, run))
    run = []
  }
  for (const bead of beads) {
    run.push(bead)
    const ends = level === 'sentence' || (level === 'turn' ? bead.turn_end : bead.paragraph_end)
    if (ends) flush()
  }
  if (run.length) flush()
  return units
}
