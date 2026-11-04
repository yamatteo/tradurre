import type { InjectionKey, Ref } from 'vue'
import type { Book, Side } from '@/api/client'
import type { Level, Unit } from '@/levels'

/** The book view's selection, provided by `BookView.vue` to every `BeadRow.vue`. */
export interface Selection {
  /** `{[current unit's id]: true}`, reactive per key: a row tracks only its own id, so a move wakes two rows. */
  currentRow: Readonly<Record<number, true>>
  /** The bead holding the current segment (corrections act on it); the current row is the unit containing it. */
  currentBeadId: Readonly<Ref<number | null>>
  currentUnit: Readonly<Ref<Unit | null>>
  currentSide: Readonly<Ref<Side>>
  currentSegmentId: Readonly<Ref<number | null>>
  editingSegmentId: Readonly<Ref<number | null>>
  /** `{[unitId]: true}` for the units of the selected run, reactive per key like `currentRow`. */
  inRun: Readonly<Record<number, true>>
  /** The selected run's 1-based unit numbers, or null without a run: for the bottom bar. */
  runBounds: Readonly<Ref<{ first: number; last: number; size: number } | null>>
  /** `{[unitId]: segmentId}` for the sentence cut with Ctrl+X, reactive per key like `currentRow`. */
  cutRow: Readonly<Record<number, number>>
  /** The book, for children that need more than the units (`MoreMenu.vue`); `BookView`'s template never reads it. */
  book: Readonly<Ref<Book | null>>
  /** The book's units at the current level, for children that summarize the run (`BookStatus.vue`). */
  units: Readonly<Ref<Unit[]>>
  level: Readonly<Ref<Level>>
}

export const selectionKey: InjectionKey<Selection> = Symbol('selection')

/** Whether the original-sentence popover is open, written by `BookView.vue` (key `o`) and read by
 * `OriginalPopover.vue` only (PLAN.md, Stage 4 render rule 1). */
export const originalKey: InjectionKey<Readonly<Ref<boolean>>> = Symbol('original')

/** The bottom bar's status message, written by `BookView.vue`'s `say()` and shown by `BookStatus.vue`: kept out of
 * the book view's template, so a message doesn't re-render the bead list (PLAN.md, Stage 4 render rule). */
export const statusKey: InjectionKey<Readonly<Ref<string>>> = Symbol('status')
