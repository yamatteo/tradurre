// Every key the book screen handles, for the shortcuts panel and for BookView's plain-key handler (PLAN.md,
// "Layout: shortcuts panel"). `key` is the `event.key` the plain-key handler matches; entries without one (Alt/Ctrl
// combinations, keys inside the sentence editor) are handled where they are, and only listed here.
// No imports: the e2e specs read this file too.

export interface Shortcut {
  id: string
  group: 'Move around' | 'Review' | 'Corrections' | 'Editing a sentence' | 'History'
  label: string
  display: string[]
  key?: string
}

export const SHORTCUTS = [
  { id: 'previous-bead', group: 'Move around', label: 'Previous bead', display: ['↑'], key: 'ArrowUp' },
  { id: 'next-bead', group: 'Move around', label: 'Next bead', display: ['↓'], key: 'ArrowDown' },
  { id: 'source-side', group: 'Move around', label: 'Source side', display: ['←'], key: 'ArrowLeft' },
  { id: 'target-side', group: 'Move around', label: 'Target side', display: ['→'], key: 'ArrowRight' },
  { id: 'next-sentence', group: 'Move around', label: 'Next / previous sentence', display: ['Tab', 'Shift+Tab'], key: 'Tab' },
  { id: 'next-problem', group: 'Move around', label: 'Next problem', display: ['P'], key: 'p' },
  { id: 'previous-problem', group: 'Move around', label: 'Previous problem', display: ['Shift+P'], key: 'P' },
  { id: 'next-unreviewed', group: 'Move around', label: 'Next unreviewed bead', display: ['N'], key: 'n' },
  { id: 'show-keys', group: 'Move around', label: 'Show this list', display: ['H'], key: 'h' },
  { id: 'reviewed', group: 'Review', label: 'Mark reviewed / unreviewed', display: ['R'], key: 'r' },
  { id: 'move-previous', group: 'Corrections', label: 'First sentence to the previous bead', display: ['Alt+↑'] },
  { id: 'move-next', group: 'Corrections', label: 'Last sentence to the next bead', display: ['Alt+↓'] },
  { id: 'merge', group: 'Corrections', label: 'Merge with the next bead', display: ['M'], key: 'm' },
  { id: 'split', group: 'Corrections', label: 'Split the bead at the sentence', display: ['S'], key: 's' },
  { id: 'exclude', group: 'Corrections', label: 'Exclude the block', display: ['X'], key: 'x' },
  { id: 'edit', group: 'Editing a sentence', label: 'Edit the sentence', display: ['Enter'], key: 'Enter' },
  { id: 'save', group: 'Editing a sentence', label: 'Save the edit', display: ['Enter'] },
  { id: 'cancel', group: 'Editing a sentence', label: 'Cancel the edit', display: ['Esc'] },
  { id: 'split-sentence', group: 'Editing a sentence', label: 'Split the sentence at the caret', display: ['Ctrl+Enter'] },
  { id: 'join', group: 'Editing a sentence', label: 'Join with the next sentence', display: ['J'], key: 'j' },
  { id: 'undo', group: 'History', label: 'Undo', display: ['Ctrl+Z'] },
  { id: 'redo', group: 'History', label: 'Redo', display: ['Ctrl+Y'] },
] as const satisfies readonly Shortcut[]

/** The shortcuts the plain-key handler dispatches: each needs a handler in `BookView.vue`. */
export type KeyedId = Extract<(typeof SHORTCUTS)[number], { key: string }>['id']
