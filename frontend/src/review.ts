// Which beads the review should look at first (SPEC §3.3; PLAN.md, "Problem navigation").
import type { BookBead } from '@/api/client'

/** Below this confidence a bead is a problem: a sentence with no counterpart usually lands in a 2:1/1:2 bead of
 * confidence ~0.4–0.45, against ≥ 0.78 for an ordinary 1:1 (PLAN.md, Stage 4). */
export const LOW_CONFIDENCE = 0.5

/** Not reviewed, and low confidence, one-sided, or (with `multi`) holding more than one segment on a side.
 * A reviewed bead is never a problem: once accepted, it stops coming back. */
export function isProblem(bead: BookBead, multi: boolean): boolean {
  if (bead.reviewed) return false
  if (bead.confidence < LOW_CONFIDENCE || !bead.source.length || !bead.target.length) return true
  return multi && (bead.source.length > 1 || bead.target.length > 1)
}
