<script setup lang="ts">
// The correction buttons for the current bead and side, in the book view's header. The selection is injected
// (like in BeadRow.vue), so moving it re-renders this bar and not the book view's 10,000-row list.
import { computed, inject } from 'vue'
import type { Book } from '@/api/client'
import { selectionKey } from '@/selection'

export type Correction = 'move-previous' | 'move-next' | 'merge' | 'split' | 'reviewed' | 'exclude'

const props = defineProps<{ book: Book; disabled: boolean }>()
const emit = defineEmits<{ correct: [action: Correction] }>()

const selection = inject(selectionKey)!
const bead = computed(() => props.book.beads.find((b) => b.id === selection.currentBeadId.value) ?? null)

const actions = computed<{ action: Correction; label: string; key: string }[]>(() => [
  { action: 'move-previous', label: '↑ first', key: 'Alt+↑' },
  { action: 'move-next', label: '↓ last', key: 'Alt+↓' },
  { action: 'merge', label: 'Merge', key: 'M' },
  { action: 'split', label: 'Split', key: 'S' },
  { action: 'reviewed', label: bead.value?.reviewed ? 'Unreviewed' : 'Reviewed', key: 'R' },
  { action: 'exclude', label: 'Exclude', key: 'X' },
])
</script>

<template>
  <div class="flex flex-wrap gap-1" data-testid="bead-actions">
    <button v-for="a in actions" :key="a.action" type="button" :data-action="a.action" :title="a.key"
      :disabled="disabled || !bead" @click="emit('correct', a.action)"
      class="px-1.5 py-0.5 text-xs border border-outline rounded bg-white text-ink hover:bg-hover disabled:opacity-50 disabled:cursor-not-allowed">
      {{ a.label }}
    </button>
  </div>
</template>
