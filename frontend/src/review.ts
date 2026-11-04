// Which units the review should look at first (SPEC §3.3; PLAN.md, "Problem navigation").
import type { BookBead } from '@/api/client'
import type { Unit } from '@/levels'

/** Below this confidence a bead is a problem: a sentence with no counterpart usually lands in a 2:1/1:2 bead of
 * confidence ~0.4–0.45, against ≥ 0.78 for an ordinary 1:1 (PLAN.md, Stage 4). */
export const LOW_CONFIDENCE = 0.5

/** Low confidence, one-sided, or (with `multi`) holding more than one segment on a side. */
export function beadLooksWrong(bead: BookBead, multi: boolean): boolean {
  if (bead.confidence < LOW_CONFIDENCE || !bead.source.length || !bead.target.length) return true
  return multi && (bead.source.length > 1 || bead.target.length > 1)
}

/** Not reviewed at its level, and some bead looks wrong. A reviewed unit is never a problem: once accepted, it stops
 * coming back. */
export function isProblem(unit: Unit, multi: boolean): boolean {
  return !unit.reviewed && unit.beads.some((b) => beadLooksWrong(b, multi))
}
