<script setup lang="ts">
// The shortcuts panel (A4): every entry of SHORTCUTS, by group. Closing is the parent's: Esc goes through its key
// handler; Close and the scrim emit `close`.
import { onMounted, ref } from 'vue'
import { SHORTCUTS, type Shortcut } from '@/keys'

const emit = defineEmits<{ close: [] }>()

const columns: Shortcut['group'][][] = [['Move around', 'Review'], ['Corrections', 'Editing a sentence', 'History']]
const entries = (group: Shortcut['group']) => SHORTCUTS.filter((s) => s.group === group)

const dialog = ref<HTMLElement | null>(null)
onMounted(() => dialog.value?.focus())
</script>

<template>
  <div class="fixed inset-0 z-40 flex items-center justify-center bg-ink/30" @click.self="emit('close')">
    <div ref="dialog" role="dialog" aria-modal="true" aria-labelledby="keys-panel-title" data-testid="keys-panel"
      tabindex="-1" class="w-[760px] max-w-[calc(100vw-32px)] max-h-[calc(100vh-32px)] overflow-auto bg-white rounded-lg shadow-xl outline-none text-[12.5px]">
      <div class="flex items-start justify-between gap-4 px-5 pt-4 pb-3 border-b border-row-rule">
        <div>
          <h2 id="keys-panel-title" class="text-[14px] font-semibold">Keyboard shortcuts</h2>
          <p class="mt-0.5 text-muted">Open this list any time with <kbd>H</kbd> or the Keys button.</p>
        </div>
        <button type="button" title="Close (Esc)" @click="emit('close')"
          class="shrink-0 h-7 px-2 flex items-center gap-1.5 rounded text-ink hover:bg-hover">
          Close <kbd>Esc</kbd>
        </button>
      </div>
      <div class="grid grid-cols-2 gap-x-8 px-5 py-4">
        <div v-for="(column, c) in columns" :key="c" class="space-y-4">
          <section v-for="group in column" :key="group">
            <h3 class="mb-1.5 text-[10.5px] uppercase tracking-wider text-faint">{{ group }}</h3>
            <div v-for="s in entries(group)" :key="s.id" data-testid="shortcut" :data-shortcut="s.id"
              class="flex items-center justify-between gap-3 py-1 border-b border-row-rule last:border-b-0">
              <span>{{ s.label }}</span>
              <span class="shrink-0 flex gap-1"><kbd v-for="d in s.display" :key="d">{{ d }}</kbd></span>
            </div>
          </section>
        </div>
      </div>
    </div>
  </div>
</template>
