import type { InjectionKey, Ref } from 'vue'
import type { Side } from '@/api/client'

/** The book view's selection, provided by `BookView.vue` to every `BeadRow.vue`. */
export interface Selection {
  /** `{[currentBeadId]: true}`, reactive per key: a row tracks only its own id, so a move wakes two rows. */
  currentRow: Readonly<Record<number, true>>
  currentBeadId: Readonly<Ref<number | null>>
  currentSide: Readonly<Ref<Side>>
  currentSegmentId: Readonly<Ref<number | null>>
  editingSegmentId: Readonly<Ref<number | null>>
}

export const selectionKey: InjectionKey<Selection> = Symbol('selection')
