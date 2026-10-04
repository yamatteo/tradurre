import type { InjectionKey, Ref } from 'vue'
import type { Book, Side } from '@/api/client'

/** The book view's selection, provided by `BookView.vue` to every `BeadRow.vue`. */
export interface Selection {
  /** `{[currentBeadId]: true}`, reactive per key: a row tracks only its own id, so a move wakes two rows. */
  currentRow: Readonly<Record<number, true>>
  currentBeadId: Readonly<Ref<number | null>>
  currentSide: Readonly<Ref<Side>>
  currentSegmentId: Readonly<Ref<number | null>>
  editingSegmentId: Readonly<Ref<number | null>>
  /** `{[beadId]: true}` for the beads of the selected run, reactive per key like `currentRow`. */
  inRun: Readonly<Record<number, true>>
  /** The selected run's 1-based bead numbers, or null without a run: for the bottom bar. */
  runBounds: Readonly<Ref<{ first: number; last: number; size: number } | null>>
  /** The book, for children that summarize the run (`BookStatus.vue`); `BookView`'s template never reads it for that. */
  book: Readonly<Ref<Book | null>>
}

export const selectionKey: InjectionKey<Selection> = Symbol('selection')

/** Whether the original-sentence popover is open, written by `BookView.vue` (key `o`) and read by
 * `OriginalPopover.vue` only (PLAN.md, Stage 4 render rule 1). */
export const originalKey: InjectionKey<Readonly<Ref<boolean>>> = Symbol('original')

/** The bottom bar's status message, written by `BookView.vue`'s `say()` and shown by `BookStatus.vue`: kept out of
 * the book view's template, so a message doesn't re-render the bead list (PLAN.md, Stage 4 render rule). */
export const statusKey: InjectionKey<Readonly<Ref<string>>> = Symbol('status')
