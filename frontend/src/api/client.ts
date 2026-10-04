const BASE = '/api/v1'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`)
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

export interface Project {
  id: string
  title: string
  source_lang: string
  target_lang: string
  created_at: string
  updated_at: string
  pair_count: number
}

export interface Pair {
  id: string
  project_id: string
  position: number
  section: number
  paragraph: number
  source_html: string
  target_html: string
  source_text: string
  target_text: string
  status: string
  created_at: string
  updated_at: string
}

export interface SearchResult {
  pair_id: string
  project_id: string
  project_title: string
  source_snippet: string
  target_snippet: string
  position: number
}

export interface SearchResponse {
  query: string
  total: number
  results: SearchResult[]
}

export interface ImportParagraph {
  html: string
  text: string
  section: number
  paragraph: number
}

export interface ImportUnit {
  html: string
  text: string
  index: number
  section: number
  paragraph: number
  confidence?: number
  method?: string
  flags?: string[]
}

export interface ImportArtifactResponse {
  title: string
  source_lang: string
  target_lang: string
  source_sentences: ImportUnit[]
  target_sentences: ImportUnit[]
  warnings: string[]
  stats: Record<string, unknown>
}

export interface ImportSectionsResponse {
  source_sections: ImportUnit[]
  target_sections: ImportUnit[]
}

export interface ImportParagraphsResponse {
  source_paragraphs: ImportUnit[]
  target_paragraphs: ImportUnit[]
}

export interface ImportSentencesResponse {
  source_sentences: ImportUnit[]
  target_sentences: ImportUnit[]
}

export interface ResplitResponse {
  pairs: Pair[]
}

export const api = {
  // Projects
  listProjects: () => request<Project[]>('/projects'),

  createProject: (data: { title: string; source_lang: string; target_lang: string }) =>
    request<Project>('/projects', { method: 'POST', body: JSON.stringify(data) }),

  getProject: (id: string) => request<Project>(`/projects/${id}`),

  deleteProject: (id: string) =>
    request<void>(`/projects/${id}`, { method: 'DELETE' }),

  // Pairs
  listPairs: (projectId: string) => request<Pair[]>(`/projects/${projectId}/pairs`),

  createPair: (projectId: string, data: { source_html: string; target_html?: string; source_text: string; target_text?: string; position?: number; section?: number; paragraph?: number }) =>
    request<Pair>(`/projects/${projectId}/pairs`, { method: 'POST', body: JSON.stringify(data) }),

  updatePair: (pairId: string, data: { source_html?: string; target_html?: string; status?: string }) =>
    request<Pair>(`/pairs/${pairId}`, { method: 'PUT', body: JSON.stringify(data) }),

  deletePair: (pairId: string) =>
    request<void>(`/pairs/${pairId}`, { method: 'DELETE' }),

  // Resplit (for paragraph/section level editing)
  resplit: (pairIds: string[], targetHtml: string) =>
    request<ResplitResponse>('/pairs/resplit', {
      method: 'POST',
      body: JSON.stringify({ pair_ids: pairIds, target_html: targetHtml }),
    }),

  // Search
  search: (q: string, lang: 'source' | 'target' | 'both' = 'both', projectId?: string) => {
    const params = new URLSearchParams({ q, lang })
    if (projectId) params.set('project_id', projectId)
    return request<SearchResponse>(`/search?${params}`)
  },

  // Import — hierarchical wizard
  importSections: async (sourceFile: File, targetFile: File): Promise<ImportSectionsResponse> => {
    const form = new FormData()
    form.append('source_file', sourceFile)
    form.append('target_file', targetFile)
    const res = await fetch(`${BASE}/import/sections`, { method: 'POST', body: form })
    if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`)
    return res.json()
  },

  importParagraphs: (sections: { source_text: string; target_text: string }[]) =>
    request<ImportParagraphsResponse>('/import/paragraphs', {
      method: 'POST',
      body: JSON.stringify({ sections }),
    }),

  importSentences: (paragraphs: { source_text: string; target_text: string; section: number; paragraph: number }[]) =>
    request<ImportSentencesResponse>('/import/sentences', {
      method: 'POST',
      body: JSON.stringify({ paragraphs }),
    }),

  importConfirm: (data: { title: string; source_lang: string; target_lang: string; pairs: { source_html: string; target_html: string; source_text: string; target_text: string; section?: number; paragraph?: number }[] }) =>
    request<Project>('/import/confirm', { method: 'POST', body: JSON.stringify(data) }),

  // Import — pre-aligned artifact (from the external embedding/LLM pipeline)
  importArtifact: async (artifactFile: File): Promise<ImportArtifactResponse> => {
    const form = new FormData()
    form.append('artifact_file', artifactFile)
    const res = await fetch(`${BASE}/import/artifact`, { method: 'POST', body: form })
    if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`)
    return res.json()
  },

  // Split/Merge
  splitPair: (pairId: string, data: { source_html_before: string; source_html_after: string; target_html_before: string; target_html_after: string }) =>
    request<Pair>(`/pairs/${pairId}/split`, { method: 'POST', body: JSON.stringify(data) }),

  mergePair: (pairId: string) =>
    request<Pair>(`/pairs/${pairId}/merge`, { method: 'POST' }),
}

// Books: projects in the new model (/api/v2; mirrors the `Book…` models in tradurre/models.py).

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

  /** The bead and up to `around` beads on each side of it. */
  context: (id: string, beadId: number, around = 2) =>
    booksRequest<ContextBead[]>(`/books/${id}/beads/${beadId}/context?around=${around}`),

  undo: (id: string) => booksPost(`/books/${id}/undo`),

  redo: (id: string) => booksPost(`/books/${id}/redo`),
}
