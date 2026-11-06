import { test, expect, type APIRequestContext } from '@playwright/test'

// The e2e database is shared by every test, and search sees all its books: each test searches for invented words
// carrying its own random tag, so other tests' books never match.
function tag() {
  return 'zq' + Math.random().toString(36).slice(2, 8).replace(/[0-9]/g, (d) => 'abcdefghij'[Number(d)]!)
}

async function importBook(request: APIRequestContext, title: string, source: string[], target: string[], beads?: number) {
  const res = await request.post('/api/v2/books', {
    multipart: {
      source: { name: 'fr.txt', mimeType: 'text/plain', buffer: Buffer.from(source.join('\n\n')) },
      target: { name: 'it.txt', mimeType: 'text/plain', buffer: Buffer.from(target.join('\n\n')) },
      title,
    },
  })
  expect(res.status()).toBe(201)
  const id: string = (await res.json()).id
  const book = await (await request.get(`/api/v2/books/${id}`)).json()
  expect(book.beads.length).toBe(beads ?? Math.max(source.length, target.length))
  return { id, book }
}

test('a word beginning finds beads in every book; Target narrows; words split across sides find nothing',
  async ({ page, request }) => {
    const t = tag()
    await importBook(request, `First ${t}`, [`Marie vit ${t}aa.`, `Il dit ${t}cc.`], [`Maria vide ${t}aa.`, `Lui disse ${t}dd.`])
    await importBook(request, `Second ${t}`, [`Paul aima ${t}aab.`], ['Paolo dormiva.'])
    const results = page.getByTestId('search-result')

    await page.goto('/search')
    await expect(page.getByTestId('search-input')).toBeFocused()
    await page.getByTestId('search-input').fill(`${t}aa`)
    await page.keyboard.press('Enter')
    await expect(results).toHaveCount(2)
    // Grouped by book, the book worked on last first.
    const groups = page.getByTestId('result-group')
    await expect(groups).toHaveText([`Second ${t} · 1 result`, `First ${t} · 1 result`])
    const second = results.nth(0)
    // The whole word is marked, not just what was typed.
    await expect(second.getByTestId('result-source').locator('mark')).toHaveText(`${t}aab`)
    await expect(second.getByTestId('result-target').locator('mark')).toHaveCount(0)
    await expect(page).toHaveURL(new RegExp(`/search\\?q=${t}aa$`))

    await page.getByTestId('search-side').selectOption('target')
    await page.getByTestId('search-submit').click()
    await expect(results).toHaveCount(1)
    await expect(groups).toHaveText([`First ${t} · 1 result`])
    await expect(page).toHaveURL(new RegExp(`side=target`))

    await page.getByTestId('search-side').selectOption('either')
    await page.getByTestId('search-input').fill(`${t}cc ${t}dd`)
    await page.keyboard.press('Enter')
    await expect(page.getByTestId('search-empty')).toHaveText('No results')
    await expect(results).toHaveCount(0)
  })

test('the book screen searches in its book; the chip scopes and its × widens', async ({ page, request }) => {
  const t = tag()
  const { id } = await importBook(request, `Scoped ${t}`, [`Une ${t}x.`], [`Una ${t}x.`])
  await importBook(request, `Other ${t}`, [`Deux ${t}y.`], [`Due ${t}y.`])
  const results = page.getByTestId('search-result')

  await page.goto(`/book/${id}`)
  await page.getByTestId('search-link').click()
  await expect(page).toHaveURL(new RegExp(`/search\\?book=${id}$`))
  await expect(page.getByTestId('search-book-chip')).toContainText(`In Scoped ${t}`)
  await page.getByTestId('search-input').fill(t)
  await page.keyboard.press('Enter')
  await expect(results).toHaveCount(1)
  await expect(page.getByTestId('result-group')).toHaveText([`Scoped ${t} · 1 result`])

  await page.getByTestId('search-book-clear').click()
  await expect(page.getByTestId('search-book-chip')).toHaveCount(0)
  await expect(results).toHaveCount(2)
  await expect(page).toHaveURL(new RegExp(`/search\\?q=${t}$`))
})

test('results come grouped by book with their counts, in reading order inside a book', async ({ page, request }) => {
  const t = tag()
  const one = await importBook(request, `Early ${t}`, [`Un ${t}.`, 'Deux.', `Trois ${t}.`], [`Uno ${t}.`, 'Due.', `Tre ${t}.`])
  const two = await importBook(request, `Late ${t}`, ['Rien.', `Quatre ${t}.`], ['Niente.', `Quattro ${t}.`])

  await page.goto(`/search?q=${t}`)
  await expect(page.getByTestId('search-summary')).toHaveText('3 results in 2 books')
  const groups = page.getByTestId('result-group')
  await expect(groups).toHaveText([`Late ${t} · 1 result`, `Early ${t} · 2 results`])
  await expect(groups.nth(0)).toHaveAttribute('data-book-id', two.id)
  await expect(groups.nth(1)).toHaveAttribute('data-book-id', one.id)
  const results = page.getByTestId('search-result')
  await expect(results).toHaveCount(3)
  for (const [k, text] of ['bead 2', 'bead 1', 'bead 3'].entries()) await expect(results.nth(k)).toContainText(text)

  await page.goto(`/search?q=${t}&book=${two.id}`)
  await expect(page.getByTestId('search-summary')).toHaveText('1 result in 1 book')
})

test('Context shows the neighbours; Open lands on the bead and Back returns to the results', async ({ page, request }) => {
  const t = tag()
  const source = ['Un.', 'Deux.', `Trois ${t}.`, 'Quatre.', 'Cinq.']
  const target = ['Uno.', 'Due.', `Tre ${t}.`, 'Quattro.', 'Cinque.']
  const { id, book } = await importBook(request, `Context ${t}`, source, target)
  const ids: number[] = book.beads.map((b: { id: number }) => b.id)
  const result = page.getByTestId('search-result')

  await page.goto(`/search?q=${t}`)
  await expect(result).toHaveCount(1)
  await expect(result).toContainText('bead 3')
  await result.getByTestId('result-context').click()
  const context = result.getByTestId('context-bead')
  await expect(context).toHaveCount(5)
  for (let k = 0; k < 5; k++) await expect(context.nth(k)).toHaveAttribute('data-bead-id', String(ids[k]))
  await expect(context.nth(0)).toContainText('Un.')
  await expect(context.nth(4)).toContainText('Cinque.')
  await expect(context.nth(2)).toHaveClass(/bg-current-side/)
  await expect(context.nth(1)).not.toHaveClass(/bg-current-side/)
  await result.getByTestId('result-context').click()
  await expect(context).toHaveCount(0)

  await result.getByTestId('result-open').click()
  await expect(page).toHaveURL(new RegExp(`/book/${id}\\?bead=${ids[2]}$`))
  await expect(page.locator('[data-testid="bead-row"][data-current="true"]')).toHaveAttribute('data-bead-id', String(ids[2]))

  await page.goBack()
  await expect(page).toHaveURL(new RegExp(`/search\\?q=${t}$`))
  await expect(page.getByTestId('search-input')).toHaveValue(t)
  await expect(result).toHaveCount(1)
})

test('a reviewed bead shows no "Not reviewed" pill', async ({ page, request }) => {
  const t = tag()
  const { id, book } = await importBook(request, `Pills ${t}`, [`Un ${t}.`, `Deux ${t}.`], [`Uno ${t}.`, `Due ${t}.`])
  const reviewed = await request.post(`/api/v2/books/${id}/reviewed`, { data: { bead_ids: [book.beads[0].id], reviewed: true } })
  expect(reviewed.status()).toBe(200)

  await page.goto(`/search?q=${t}`)
  const results = page.getByTestId('search-result')
  await expect(results).toHaveCount(2)
  await expect(page.locator(`[data-testid="search-result"][data-bead-id="${book.beads[0].id}"]`)
    .getByTestId('result-unreviewed')).toHaveCount(0)
  await expect(page.locator(`[data-testid="search-result"][data-bead-id="${book.beads[1].id}"]`)
    .getByTestId('result-unreviewed')).toHaveText('Not reviewed')
})

test('60 matches show 50, then More results shows all 60', async ({ page, request }) => {
  const t = tag()
  const n = 60
  const source = Array.from({ length: n }, (_, k) => `Phrase ${k} ${t}.`)
  const target = Array.from({ length: n }, (_, k) => `Frase ${k} ${t}.`)
  await importBook(request, `Many ${t}`, source, target)

  await page.goto(`/search?q=${t}`)
  const results = page.getByTestId('search-result')
  await expect(results).toHaveCount(50)
  await page.getByTestId('search-more').click()
  await expect(results).toHaveCount(60)
  await expect(page.getByTestId('search-more')).toHaveCount(0)
})

test('a result reviewed in its turn or paragraph says so; sentence and unreviewed results keep their badges', async ({ page, request }) => {
  const t = tag()
  const { id, book } = await importBook(request, `Levels ${t}`, [`Un ${t}.`, `Deux ${t}.`, `Trois ${t}.`], [`Uno ${t}.`, `Due ${t}.`, `Tre ${t}.`])
  const ids: number[] = book.beads.map((b: { id: number }) => b.id)
  for (const [bead, level] of [[ids[0], 'turn'], [ids[1], 'paragraph']] as const) {
    const res = await request.post(`/api/v2/books/${id}/reviewed`, { data: { bead_ids: [bead], reviewed: true, level } })
    expect(res.status()).toBe(200)
  }
  const res = await request.post(`/api/v2/books/${id}/reviewed`, { data: { bead_ids: [ids[2]], reviewed: true } })
  expect(res.status()).toBe(200)

  await page.goto(`/search?q=${t}`)
  await expect(page.getByTestId('search-result')).toHaveCount(3)
  const of = (bead: number) => page.locator(`[data-testid="search-result"][data-bead-id="${bead}"]`)
  await expect(of(ids[0]).getByTestId('result-review-level')).toHaveText('Reviewed in its turn')
  await expect(of(ids[0]).getByTestId('result-review-level')).toHaveAttribute('data-level', 'turn')
  await expect(of(ids[1]).getByTestId('result-review-level')).toHaveText('Reviewed in its paragraph')
  await expect(of(ids[1]).getByTestId('result-review-level')).toHaveAttribute('data-level', 'paragraph')
  await expect(of(ids[2]).getByTestId('result-review-level')).toHaveCount(0)
  await expect(of(ids[2]).getByTestId('result-unreviewed')).toHaveCount(0)
  await expect(page.getByTestId('result-unreviewed')).toHaveCount(0)
})

test('an unreviewed result in a multi-bead turn shows the whole turn as its context', async ({ page, request }) => {
  const t = tag()
  const { book } = await importBook(request, `Turn ${t}`,
    ['Un.', 'Deux.', `— Trois ${t}. Quatre. Cinq.`, 'Six.', 'Sept.'], ['Uno.', 'Due.', `— Tre ${t}. Quattro. Cinque.`, 'Sei.', 'Sette.'], 7)
  const ids: number[] = book.beads.map((b: { id: number }) => b.id)
  expect(ids.length).toBe(7)
  await page.goto(`/search?q=${t}`)
  const result = page.getByTestId('search-result')
  await expect(result).toHaveCount(1)
  await result.getByTestId('result-context').click()
  const context = result.getByTestId('context-bead')
  // The frontend asks for 2 beads around: the turn (beads 3 to 5) plus two on each side is the whole book.
  await expect(context).toHaveCount(7)
  for (let k = 0; k < 7; k++) await expect(context.nth(k)).toHaveAttribute('data-bead-id', String(ids[k]))
  for (const k of [0, 1, 5, 6]) await expect(context.nth(k)).not.toHaveAttribute('data-in-turn', 'true')
  for (const k of [2, 3, 4]) await expect(context.nth(k)).toHaveAttribute('data-in-turn', 'true')
  await expect(context.nth(2)).toHaveClass(/bg-current-side/)
  await expect(context.nth(3)).not.toHaveClass(/text-muted/)
  await expect(context.nth(1)).toHaveClass(/text-muted/)
})

test('Whole words drops longer words, keeps the exact one, and lives in the URL', async ({ page, request }) => {
  const t = tag()
  await importBook(request, `Whole ${t}`, [`Un ${t}bello.`, `Un ${t}bellezza.`], [`Uno ${t}a.`, `Uno ${t}b.`])
  const results = page.getByTestId('search-result')

  await page.goto('/search')
  await page.getByTestId('search-input').fill(`${t}bell`)
  await page.keyboard.press('Enter')
  await expect(results).toHaveCount(2)

  await page.getByTestId('search-input').fill(`${t}bello`)
  await page.getByTestId('search-whole').check()
  await page.getByTestId('search-submit').click()
  await expect(results).toHaveCount(1)
  await expect(results.getByTestId('result-source').locator('mark')).toHaveText(`${t}bello`)
  await expect(page).toHaveURL(/whole=1/)

  await page.reload()
  await expect(page.getByTestId('search-whole')).toBeChecked()
  await expect(results).toHaveCount(1)
})
