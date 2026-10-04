<script setup lang="ts">
// The second bar's review group or corrections group, for the current bead and side. The selection is injected
// (like in BeadRow.vue), so moving it re-renders these buttons and not the book view's 10,000-row list.
import { computed, inject } from 'vue'
import type { Book } from '@/api/client'
import { selectionKey } from '@/selection'

export type Correction =
  | 'move-previous' | 'move-next' | 'merge' | 'split' | 'edit' | 'join' | 'reviewed' | 'up-to-here' | 'exclude'

const props = defineProps<{ book: Book; disabled: boolean; group: 'review' | 'corrections' }>()
const emit = defineEmits<{ correct: [action: Correction] }>()

const selection = inject(selectionKey)!
const bead = computed(() => props.book.beads.find((b) => b.id === selection.currentBeadId.value) ?? null)

const actions = computed<{ action: Correction; label: string; key: string; testid?: string }[]>(() =>
  props.group === 'review'
    ? [
        { action: 'reviewed', label: bead.value?.reviewed ? 'Unreviewed' : 'Reviewed', key: 'R' },
        { action: 'up-to-here', label: 'Up to here', key: 'Shift+R', testid: 'reviewed-up-to-here' },
      ]
    : [
        { action: 'move-previous', label: 'To previous', key: 'Alt+↑' },
        { action: 'move-next', label: 'To next', key: 'Alt+↓' },
        { action: 'merge', label: 'Merge', key: 'M' },
        { action: 'split', label: 'Split', key: 'S' },
        { action: 'edit', label: 'Edit', key: 'Enter' },
        { action: 'join', label: 'Join', key: 'J' },
        { action: 'exclude', label: 'Exclude', key: 'X' },
      ],
)
</script>

<template>
  <div class="flex items-center gap-0.5" :data-testid="group === 'corrections' ? 'bead-actions' : undefined">
    <button v-for="a in actions" :key="a.action" type="button" :data-action="a.action" :data-testid="a.testid" :title="`${a.label} (${a.key})`"
      :disabled="disabled || !bead" @click="emit('correct', a.action)"
      class="h-7 px-2 flex items-center gap-1.5 rounded text-ink hover:bg-hover disabled:opacity-40 disabled:hover:bg-transparent disabled:cursor-not-allowed">
      {{ a.label }} <kbd>{{ a.key }}</kbd>
    </button>
  </div>
</template>
