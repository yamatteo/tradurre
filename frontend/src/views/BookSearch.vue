<script setup lang="ts">
// Search across every book, or one (SPEC §3.4; PLAN.md, "Search page"). The URL holds the state (`?q=&side=&book=`),
// so Back from a book opens the same results again.
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { booksApi, type BookSearchCount, type BookSearchResult, type BookSummary, type ContextBead, type SearchSide } from '@/api/client'

const PAGE = 50
const SIDES: { value: SearchSide; label: string }[] = [
  { value: 'either', label: 'Either side' },
  { value: 'source', label: 'Source' },
  { value: 'target', label: 'Target' },
]

const route = useRoute()
const router = useRouter()

const query = ref('')
const side = ref<SearchSide>('either')
const bookId = ref<string | null>(null)
const books = ref<BookSummary[]>([])
const bookTitle = computed(() => books.value.find((b) => b.id === bookId.value)?.title ?? '…')

const results = ref<BookSearchResult[] | null>(null)
// Matches per book, for the summary and the group headers.
const counts = ref<BookSearchCount[]>([])
const countOf = computed(() => new Map(counts.value.map((c) => [c.book_id, c.count])))
const summary = computed(() => {
  const n = counts.value.reduce((sum, c) => sum + c.count, 0)
  const m = counts.value.length
  return `${n} ${n === 1 ? 'result' : 'results'} in ${m} ${m === 1 ? 'book' : 'books'}`
})
// Whether the last page was full, so there may be more.
const more = ref(false)
const loading = ref(false)
const error = ref('')
// The open contexts, by the result's bead id.
const contexts = reactive(new Map<number, ContextBead[]>())
const input = ref<HTMLInputElement | null>(null)
// A newer search makes the answers of older ones stale.
let generation = 0

function one(value: unknown): string | null {
  const v = Array.isArray(value) ? value[0] : value
  return typeof v === 'string' && v !== '' ? v : null
}

async function run(offset = 0) {
  const q = query.value.trim()
  const mine = ++generation
  error.value = ''
  if (!offset) contexts.clear()
  if (!q) {
    results.value = null
    counts.value = []
    more.value = false
    return
  }
  loading.value = true
  try {
    const book = bookId.value ?? undefined
    const [page, found] = await Promise.all([
      booksApi.search(q, side.value, book, offset),
      offset ? null : booksApi.searchCounts(q, side.value, book),
    ])
    if (mine !== generation) return
    if (found) counts.value = found
    results.value = offset ? [...(results.value ?? []), ...page] : page
    more.value = page.length === PAGE
  } catch (e) {
    if (mine === generation) error.value = (e as Error).message
  } finally {
    if (mine === generation) loading.value = false
  }
}

function submit() {
  const q = query.value.trim()
  router.replace({
    query: {
      ...(q ? { q } : {}),
      ...(side.value !== 'either' ? { side: side.value } : {}),
      ...(bookId.value ? { book: bookId.value } : {}),
    },
  })
  run()
}

function widen() {
  bookId.value = null
  submit()
}

async function toggleContext(result: BookSearchResult) {
  if (contexts.has(result.bead_id)) {
    contexts.delete(result.bead_id)
    return
  }
  try {
    contexts.set(result.bead_id, await booksApi.context(result.book_id, result.bead_id, 2))
  } catch (e) {
    error.value = (e as Error).message
  }
}

onMounted(async () => {
  query.value = one(route.query.q) ?? ''
  const s = one(route.query.side)
  side.value = SIDES.some((o) => o.value === s) ? (s as SearchSide) : 'either'
  bookId.value = one(route.query.book)
  input.value?.focus()
  run()
  if (bookId.value) {
    try {
      books.value = await booksApi.listBooks()
    } catch {
      // The chip then shows "…"; the search itself still works.
    }
  }
})
</script>

<template>
  <div class="min-h-screen bg-ground font-ui text-ink text-[13px]">
    <div class="max-w-5xl mx-auto px-4 py-6">
      <form class="flex flex-wrap items-center gap-2" @submit.prevent="submit">
        <input ref="input" v-model="query" type="search" data-testid="search-input" placeholder="Search the books…"
          class="flex-1 min-w-[200px] h-9 px-3 bg-white border border-outline rounded font-text text-[15px] focus:outline-none focus:border-accent" />
        <select v-model="side" data-testid="search-side"
          class="h-9 px-2 bg-white border border-outline rounded focus:outline-none focus:border-accent">
          <option v-for="o in SIDES" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
        <button type="submit" data-testid="search-submit"
          class="h-9 px-4 rounded bg-accent text-white font-medium hover:opacity-90">Search</button>
      </form>
      <p v-if="bookId" class="mt-2">
        <span data-testid="search-book-chip"
          class="inline-flex items-center gap-1.5 h-7 pl-2.5 pr-1 rounded-full bg-current-side border border-outline">
          In {{ bookTitle }}
          <button type="button" data-testid="search-book-clear" aria-label="Search all books" title="Search all books"
            class="w-5 h-5 flex items-center justify-center rounded-full text-muted hover:bg-hover" @click="widen">
            <svg width="8" height="8" viewBox="0 0 10 10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true">
              <path d="M1 1l8 8M9 1l-8 8" />
            </svg>
          </button>
        </span>
      </p>

      <p v-if="error" class="mt-4 text-problem">{{ error }}</p>
      <p v-if="results && !results.length" data-testid="search-empty" class="mt-6 text-muted">No results</p>

      <p v-if="results?.length" data-testid="search-summary" class="mt-4 text-muted">{{ summary }}</p>

      <ul v-if="results?.length" class="mt-2 space-y-3">
        <template v-for="(r, i) in results" :key="r.bead_id">
        <li v-if="i === 0 || results[i - 1]!.book_id !== r.book_id" data-testid="result-group" :data-book-id="r.book_id"
          class="pt-3 first:pt-0 flex items-baseline gap-2">
          <span class="font-semibold text-[14px] truncate">{{ r.title }}</span> <span class="text-faint">· {{ countOf.get(r.book_id) ?? '…' }} {{ countOf.get(r.book_id) === 1 ? 'result' : 'results' }}</span>
        </li>
        <li data-testid="search-result" :data-bead-id="r.bead_id"
          class="bg-list border border-bar-rule rounded-md">
          <div class="flex items-center gap-2 px-3 h-9 border-b border-row-rule text-[12.5px]">
            <span class="text-faint">bead {{ r.position }}</span>
            <span v-if="!r.reviewed" data-testid="result-unreviewed"
              class="px-1.5 rounded-full bg-pill text-pill-ink text-[11px] font-medium">Not reviewed</span>
            <span class="flex-1" />
            <button type="button" data-testid="result-context" :aria-expanded="contexts.has(r.bead_id)"
              class="h-7 px-2 rounded text-ink hover:bg-hover" :class="contexts.has(r.bead_id) ? 'bg-hover' : ''"
              @click="toggleContext(r)">Context</button>
            <router-link :to="`/book/${r.book_id}?bead=${r.bead_id}`" data-testid="result-open"
              class="h-7 px-2 flex items-center rounded text-accent hover:bg-hover">Open</router-link>
          </div>
          <div class="grid grid-cols-2 gap-4 px-3 py-2 font-text text-[15px] leading-relaxed">
            <p data-testid="result-source">
              <template v-for="(s, i) in r.source" :key="i"><mark v-if="s.match">{{ s.text }}</mark><template v-else>{{ s.text }}</template></template>
            </p>
            <p data-testid="result-target">
              <template v-for="(s, i) in r.target" :key="i"><mark v-if="s.match">{{ s.text }}</mark><template v-else>{{ s.text }}</template></template>
            </p>
          </div>
          <div v-if="contexts.has(r.bead_id)" data-testid="result-context-beads" class="border-t border-row-rule">
            <div v-for="c in contexts.get(r.bead_id)" :key="c.bead_id" data-testid="context-bead" :data-bead-id="c.bead_id"
              class="grid grid-cols-2 gap-4 px-3 py-1.5 font-text text-[14px] leading-relaxed"
              :class="c.bead_id === r.bead_id ? 'bg-current-side' : 'text-muted'">
              <p>{{ c.source }}</p>
              <p>{{ c.target }}</p>
            </div>
          </div>
        </li>
        </template>
      </ul>

      <button v-if="results?.length && more" type="button" data-testid="search-more" :disabled="loading"
        class="mt-4 h-9 px-4 rounded border border-outline bg-white hover:bg-hover disabled:opacity-50"
        @click="run(results.length)">More results</button>
    </div>
  </div>
</template>
