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

export interface ImportPreviewResponse {
  source_paragraphs: ImportParagraph[]
  target_paragraphs: ImportParagraph[]
}

export interface ImportUnit {
  html: string
  text: string
  index: number
  section: number
  paragraph: number
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

  // Import — legacy
  importPreview: async (sourceFile: File, targetFile: File): Promise<ImportPreviewResponse> => {
    const form = new FormData()
    form.append('source_file', sourceFile)
    form.append('target_file', targetFile)
    const res = await fetch(`${BASE}/import/preview`, { method: 'POST', body: form })
    if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`)
    return res.json()
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

  // Split/Merge
  splitPair: (pairId: string, data: { source_html_before: string; source_html_after: string; target_html_before: string; target_html_after: string }) =>
    request<Pair>(`/pairs/${pairId}/split`, { method: 'POST', body: JSON.stringify(data) }),

  mergePair: (pairId: string) =>
    request<Pair>(`/pairs/${pairId}/merge`, { method: 'POST' }),
}
