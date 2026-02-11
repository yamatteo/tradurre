# Literary Translation Workbench — Implementation Plan

## Context

Literary translators need a tool that respects their workflow: paragraph-level alignment between source and translation, flexible views (side-by-side or interleaved), and the ability to search how any word was translated in the past across all their works. Existing CAT tools (OmegaT, memoQ, Trados) are designed for technical/legal translation with rigid sentence-level segmentation — they don't fit literary prose. No existing open-source tool covers this combination of features well enough.

We'll build a **webapp** called `tradurre` (working name) — a FastAPI backend with a Vue 3 + TipTap frontend, running locally as a solo-translator tool. The project lives as a new uv workspace member in a subfolder of `/media/yamatteo/Storage/py312/`.

---

## Architecture

```
Browser (localhost:8000)
  └─ Vue 3 SPA + TipTap editors
       │
       ▼  (REST API)
  FastAPI (Python)
       │
       ▼
  SQLite + FTS5 (~/.tradurre/tradurre.db)
```

- **Fully local, offline-capable.** A single `uv run tradurre` command starts everything.
- **FastAPI** serves both the API and the pre-built Vue SPA from `frontend/dist/`.
- **SQLite with FTS5** handles storage and full-text reverse search in one file.
- During development: Vite dev server (port 5173) proxies API calls to FastAPI (port 8000).

---

## Tech Stack

**Backend (Python 3.12)**
- `fastapi` + `uvicorn` — REST API
- `sqlite3` (stdlib) with FTS5 — storage + full-text search
- `python-docx` — parse `.docx` paragraph structure
- `pydantic` — request/response validation

**Frontend (TypeScript)**
- Vue 3 (Composition API, `<script setup>`)
- TipTap (`@tiptap/vue-3`) — ProseMirror-based rich text editor
- Vite — build tool
- Tailwind CSS — styling

---

## Data Model (SQLite)

```sql
CREATE TABLE projects (
    id          TEXT PRIMARY KEY,        -- UUID
    title       TEXT NOT NULL,
    source_lang TEXT NOT NULL,           -- ISO 639-1
    target_lang TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE pairs (
    id          TEXT PRIMARY KEY,        -- UUID
    project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,        -- ordering within project
    source_html TEXT NOT NULL,           -- rich text for TipTap
    target_html TEXT NOT NULL DEFAULT '',
    source_text TEXT NOT NULL,           -- plain text for FTS indexing
    target_text TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'draft',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    UNIQUE(project_id, position)
);

-- FTS5 virtual table for reverse search (external content, synced via triggers)
CREATE VIRTUAL TABLE translation_memory USING fts5(
    source_text, target_text,
    project_id UNINDEXED, pair_id UNINDEXED,
    content=pairs, content_rowid=rowid,
    tokenize='unicode61 remove_diacritics 2'
);
-- + INSERT/UPDATE/DELETE triggers to keep FTS5 in sync with pairs
```

**Key decisions:**
- Dual storage: `*_html` for editor rendering, `*_text` for search indexing
- External-content FTS5 avoids duplicating data
- `unicode61 remove_diacritics 2` tokenizer handles European languages with accent folding
- UUID primary keys allow client-side ID generation

---

## Core Features

### 1. Paragraph-Aligned Editor

Two TipTap editor instances (source + target) with two view modes:

- **Side-by-side:** Two scrollable columns. Scroll sync keeps corresponding paragraphs aligned — when you scroll one column, the other follows to show the matching paragraph at the same viewport position.
- **Interleaved:** A single scrollable list where each item shows source paragraph above, target editing area below.

The source editor is read-only (or lightly editable for corrections). The target editor is the primary workspace. Minimal toolbar: bold, italic, underline, undo/redo — nothing else to distract from prose.

Auto-save: debounced 1.5s after last keystroke, with visual "Saved" indicator.

### 2. Reverse Search (Translation Memory)

Search any word/phrase → get all past (source, target) pairs containing it, across all projects, with highlighted context snippets.

- Backend: FTS5 `MATCH` query with `snippet()` for context extraction
- Can filter by: source only, target only, or both; optionally restrict to one project
- Frontend: search bar with debounced queries, results as cards showing source + target snippets with project name and paragraph number; click to jump to that paragraph in the editor

### 3. Import Existing Parallel Texts

Two-step flow:
1. **Upload** source + target files (`.docx` or `.txt`) → server extracts paragraphs and returns an alignment preview
2. **Adjust** alignment in the browser (split/merge/insert blank paragraphs) → confirm creates the project

Paragraph detection: `.docx` uses Word's native paragraph structure; `.txt` splits on blank lines.

---

## Project Structure

```
tradurre/                          # new subfolder in /media/yamatteo/Storage/py312/
  pyproject.toml                   # uv workspace member
  tradurre/
    __init__.py
    __main__.py                    # entry point: starts uvicorn
    app.py                         # FastAPI app, CORS, static mount
    config.py                      # settings (db path, host, port)
    db.py                          # SQLite connection, schema, FTS5 triggers
    models.py                      # Pydantic models
    api/
      projects.py                  # Project CRUD
      pairs.py                     # Pair CRUD + auto-save endpoint
      search.py                    # Reverse search endpoint
      import_.py                   # Import upload + confirm
    services/
      importer.py                  # .docx/.txt parsing, paragraph extraction
      html_utils.py                # HTML ↔ plain text stripping
  frontend/
    package.json
    vite.config.ts
    tailwind.config.js
    src/
      App.vue
      router.ts
      views/
        ProjectList.vue            # dashboard
        ProjectEditor.vue          # main translation workspace
        SearchView.vue             # global reverse search page
      components/
        editor/
          TranslationEditor.vue    # orchestrates two-pane editor
          ParagraphPair.vue        # single pair (for interleaved mode)
          ScrollSync.ts            # scroll synchronization logic
        import/
          ImportWizard.vue         # multi-step import flow
          AlignmentPreview.vue     # preview + adjust alignment
        search/
          SearchBar.vue
          SearchResults.vue
      composables/
        useApi.ts                  # thin fetch wrapper
        useScrollSync.ts           # scroll sync composable
        useDebounce.ts
    dist/                          # built output (served by FastAPI)
```

---

## Implementation Phases

### Phase 1: Foundation
1. Create `tradurre/` subfolder, `pyproject.toml`, register in root workspace
2. Implement `db.py` — SQLite schema + FTS5 virtual table + triggers
3. Implement Pydantic models and FastAPI app skeleton
4. Project and Pair CRUD endpoints
5. Scaffold Vue 3 + Vite + TipTap frontend

### Phase 2: Editor Core
6. `TranslationEditor.vue` — load pairs, render two TipTap editors
7. Side-by-side mode with scroll synchronization
8. Interleaved mode
9. Auto-save with debounce

### Phase 3: Import
10. Backend: `.docx` and `.txt` paragraph extraction
11. Import API endpoints (upload → preview → confirm)
12. Frontend: `ImportWizard.vue` with alignment preview and adjust controls

### Phase 4: Reverse Search
13. Search API endpoint with FTS5 queries
14. Frontend: `SearchView.vue` with highlighted snippets
15. Inline search from editor (select text → search in TM)

### Phase 5: Polish
16. Keyboard shortcuts, paragraph split/merge, status tracking
17. Export to `.docx` or plain text
18. Performance: virtualize paragraph list for large works if needed

---

## Verification Plan

1. **Backend:** Start server with `uv run tradurre`, create a project via API, add pairs, verify FTS5 search returns correct snippets with `curl`
2. **Import:** Import two `.docx` test files, verify paragraph alignment in the browser
3. **Editor:** Open a project, type in the target editor, switch between side-by-side and interleaved views, verify auto-save persists on page reload
4. **Reverse search:** Translate several paragraphs across 2+ projects, search for a word, verify results show pairs from both projects with context
5. **Scroll sync:** Import a long work (50+ paragraphs), verify side-by-side scroll keeps corresponding paragraphs visible together
