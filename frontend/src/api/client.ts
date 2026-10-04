// The books API (/api/v2; mirrors the `Book…` models in tradurre/models.py).

const BOOKS_BASE = '/api/v2'

async function booksRequest<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BOOKS_BASE}${path}`, options)
  if (!res.ok) {
    // The server's `detail` is meant for the translator (e.g. why a correction was refused).
    let message = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') message = body.detail
    } catch {
      // not JSON: keep the status line
    }
    throw new Error(message)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

/** A correction: POST with an optional JSON body; the server returns the whole corrected book. */
function booksPost(path: string, body?: unknown): Promise<Book> {
  return booksRequest<Book>(path, {
    method: 'POST',
    ...(body === undefined ? {} : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  })
}

export type Side = 'source' | 'target'

export interface BookImportResponse {
  id: string
  title: string
  bead_count: number
  warnings: string[]
}

export interface BookSummary {
  id: string
  title: string
  source_lang: string
  target_lang: string
  bead_count: number
  reviewed_count: number
}

export interface BookSegment {
  segment_id: number
  block_id: number
  block_kind: string
  text: string
  /** The extracted text, only when it differs from `text` (the sentence is edited); else null. */
  original: string | null
}

export interface BookBead {
  id: number
  confidence: number
  method: string
  reviewed: boolean
  source: BookSegment[]
  target: BookSegment[]
}

export interface BookExcludedSegment {
  segment_id: number
  text: string
}

export interface BookExcludedBlock {
  block_id: number
  side: Side
  kind: string
  page: number | null
  segments: BookExcludedSegment[]
  after_bead_id: number | null
}

export interface Book {
  id: string
  title: string
  source_lang: string
  target_lang: string
  beads: BookBead[]
  excluded: BookExcludedBlock[]
  can_undo: boolean
  can_redo: boolean
}

export interface BookRunWarning {
  side: Side | null
  message: string
}

/** What an import (or, later, an alignment run) did: counts and timings in `stats`, and its warnings. */
export interface BookRun {
  id: number
  kind: string
  created_at: string
  app_version: string
  stats: Record<string, unknown>
  warnings: BookRunWarning[]
}

/** A piece of a search result's text; `match` marks what the query matched. */
export interface BookSearchSpan {
  text: string
  match: boolean
}

/** How many beads in one book match a search. */
export interface BookSearchCount {
  book_id: string
  title: string
  count: number
}

export interface BookSearchResult {
  bead_id: number
  book_id: string
  title: string
  position: number
  source: BookSearchSpan[]
  target: BookSearchSpan[]
  reviewed: boolean
}

export type SearchSide = Side | 'either'

/** A bead around a search result, as plain text per side. */
export interface ContextBead {
  bead_id: number
  position: number
  source: string
  target: string
  reviewed: boolean
}

export const booksApi = {
  importBook: (source: File, target: File, title: string, sourceLang: string, targetLang: string) => {
    const form = new FormData()
    form.append('source', source)
    form.append('target', target)
    form.append('title', title)
    form.append('source_lang', sourceLang)
    form.append('target_lang', targetLang)
    return booksRequest<BookImportResponse>('/books', { method: 'POST', body: form })
  },

  listBooks: () => booksRequest<BookSummary[]>('/books'),

  getBook: (id: string) => booksRequest<Book>(`/books/${id}`),

  /** Delete the book and everything in it; it can't be undone. */
  deleteBook: (id: string) => booksRequest<void>(`/books/${id}`, { method: 'DELETE' }),

  getRuns: (id: string) => booksRequest<BookRun[]>(`/books/${id}/runs`),

  move: (id: string, beadId: number, side: Side, to: 'previous' | 'next') =>
    booksPost(`/books/${id}/beads/${beadId}/move`, { side, to }),

  mergeNext: (id: string, beadId: number) => booksPost(`/books/${id}/beads/${beadId}/merge-next`),

  splitBead: (id: string, beadId: number, sourceAt: number | null, targetAt: number | null) =>
    booksPost(`/books/${id}/beads/${beadId}/split`, { source_at: sourceAt, target_at: targetAt }),

  setReviewed: (id: string, beadIds: number[], reviewed: boolean) =>
    booksPost(`/books/${id}/reviewed`, { bead_ids: beadIds, reviewed }),

  excludeBlock: (id: string, blockId: number) => booksPost(`/books/${id}/blocks/${blockId}/exclude`),

  includeBlock: (id: string, blockId: number) => booksPost(`/books/${id}/blocks/${blockId}/include`),

  /** Exclude every block of `side` from the start of the edition up to the bead (`to: 'start'`), or from it to the end. */
  excludeRange: (id: string, beadId: number, side: Side, to: 'start' | 'end') =>
    booksPost(`/books/${id}/blocks/exclude-range`, { bead_id: beadId, side, to }),

  /** Include the excluded blocks of that range, except running heads, page numbers and footnotes. */
  includeRange: (id: string, beadId: number, side: Side, to: 'start' | 'end') =>
    booksPost(`/books/${id}/blocks/include-range`, { bead_id: beadId, side, to }),

  editSegment: (id: string, segmentId: number, text: string) =>
    booksPost(`/books/${id}/segments/${segmentId}/edit`, { text }),

  splitSegment: (id: string, segmentId: number, offset: number) =>
    booksPost(`/books/${id}/segments/${segmentId}/split`, { offset }),

  joinNext: (id: string, segmentId: number) => booksPost(`/books/${id}/segments/${segmentId}/join-next`),

  /** Re-align the beads from `firstBeadId` to `lastBeadId` with the aligner; the new beads start unreviewed. */
  realign: (id: string, firstBeadId: number, lastBeadId: number) =>
    booksPost(`/books/${id}/beads/realign`, { first_bead_id: firstBeadId, last_bead_id: lastBeadId }),

  /** Put the segment's original extracted text back. */
  restoreOriginal: (id: string, segmentId: number) => booksPost(`/books/${id}/segments/${segmentId}/restore`),

  /** Beads matching `q` (word beginnings, case and accents folded), in every book or in `book`; 50 per page. */
  search: (q: string, side: SearchSide = 'either', book?: string, offset = 0) => {
    const params = new URLSearchParams({ q, side, offset: String(offset) })
    if (book) params.set('book', book)
    return booksRequest<BookSearchResult[]>(`/search?${params}`)
  },

  /** The number of matching beads per book, books in the order `search` returns them. */
  searchCounts: (q: string, side: SearchSide = 'either', book?: string) => {
    const params = new URLSearchParams({ q, side })
    if (book) params.set('book', book)
    return booksRequest<BookSearchCount[]>(`/search/books?${params}`)
  },

  /** The edition export's URL, for a download link: one side's text as reviewed (the server names the file). */
  editionUrl: (id: string, side: Side, format: 'txt' | 'docx') =>
    `${BOOKS_BASE}/books/${id}/export/edition?side=${side}&format=${format}`,

  /** The project bundle's URL, for a download link: the book's text layer and alignment as a backup. */
  bundleUrl: (id: string) => `${BOOKS_BASE}/books/${id}/export/bundle`,

  /** Restore a bundle as a new book (titled "… (restored <date>)" next to a book with the same title). */
  importBundle: (bundle: File) => {
    const form = new FormData()
    form.append('bundle', bundle)
    return booksRequest<BookImportResponse>('/books/bundle', { method: 'POST', body: form })
  },

  /** The bead and up to `around` beads on each side of it. */
  context: (id: string, beadId: number, around = 2) =>
    booksRequest<ContextBead[]>(`/books/${id}/beads/${beadId}/context?around=${around}`),

  undo: (id: string) => booksPost(`/books/${id}/undo`),

  redo: (id: string) => booksPost(`/books/${id}/redo`),
}
