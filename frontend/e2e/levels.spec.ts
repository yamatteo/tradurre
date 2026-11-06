import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

// Invented words. Beads after import, all 1:1: N1 (narrative), S1 and S2 (the two sentences of a speech paragraph,
// opening with a dash: one turn), N2 (narrative). So: sentences 4 rows, turns 3 rows (N1, S1+S2, N2), paragraphs 3 rows.
const SOURCE = 'Marie arriva dans la vallée.\n\n— Zorbe lunai tu vanet. Il pleuvait sur la route.\n\nPaul partit sans un mot.'
const TARGET = 'Maria arrivò nella valle.\n\n— Zorba lunai tu vanet. Pioveva sulla strada.\n\nPaolo partì senza una parola.'

async function importBook(request: APIRequestContext, title: string) {
  const res = await request.post('/api/v2/books', {
    multipart: {
      source: { name: 'fr.txt', mimeType: 'text/plain', buffer: Buffer.from(SOURCE) },
      target: { name: 'it.txt', mimeType: 'text/plain', buffer: Buffer.from(TARGET) },
      title,
    },
  })
  expect(res.status()).toBe(201)
  const id: string = (await res.json()).id
  const book = await getBook(request, id)
  expect(book.beads.map((b: Bead) => [b.source.length, b.target.length, b.turn_end, b.paragraph_end])).toEqual([
    [1, 1, true, true], [1, 1, false, false], [1, 1, true, true], [1, 1, true, true],
  ])
  return { id, beads: book.beads as Bead[] }
}

interface Bead {
  id: number
  review_level: string | null
  turn_end: boolean
  paragraph_end: boolean
  source: { segment_id: number; text: string }[]
  target: { text: string }[]
}

async function getBook(request: APIRequestContext, id: string) {
  return (await request.get(`/api/v2/books/${id}`)).json()
}

function current(page: Page) {
  return page.locator('[data-testid="bead-row"][data-current="true"]')
}

function row(page: Page, unitId: number) {
  return page.locator(`[data-testid="bead-row"][data-bead-id="${unitId}"]`)
}

async function open(page: Page, id: string) {
  await page.goto(`/book/${id}`)
  await expect(current(page)).toBeVisible()
}

function level(page: Page, name: string) {
  return page.getByTestId('level').locator(`[data-level="${name}"]`)
}

test('the book opens at turns; L cycles the level and the control shows it', async ({ page, request }) => {
  const { id } = await importBook(request, 'Level cycle')
  await open(page, id)
  await expect(level(page, 'turn')).toHaveAttribute('aria-pressed', 'true')
  await expect(level(page, 'sentence')).toHaveAttribute('aria-pressed', 'false')
  await expect(page.getByTestId('bead-row')).toHaveCount(3)
  await page.keyboard.press('l')
  await expect(level(page, 'paragraph')).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByTestId('bead-row')).toHaveCount(3)
  await page.keyboard.press('l')
  await expect(level(page, 'sentence')).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByTestId('bead-row')).toHaveCount(4)
  await page.keyboard.press('l')
  await expect(level(page, 'turn')).toHaveAttribute('aria-pressed', 'true')
  await level(page, 'sentence').click()
  await expect(page.getByTestId('bead-row')).toHaveCount(4)
  await expect(page.getByTestId('position')).toHaveText(/^Bead 1 of 4 · Source · sentence 1 of 1$/)
})

test('the speech paragraph is one row at turns, two at sentences, and the current unit follows the bead', async ({ page, request }) => {
  const { id, beads } = await importBook(request, 'Speech rows')
  const [, s1, s2] = beads
  await open(page, id)
  await expect(row(page, s1!.id).locator('[data-segment-id]')).toHaveCount(4)
  await expect(row(page, s1!.id)).toContainText('Zorbe lunai tu vanet.')
  await expect(row(page, s2!.id)).toHaveCount(0)
  await page.keyboard.press('ArrowDown')
  await expect(current(page)).toHaveAttribute('data-bead-id', String(s1!.id))
  await expect(page.getByTestId('position')).toHaveText(/^Turn 2 of 3 · Source · sentence 1 of 2$/)
  await page.keyboard.press('Tab')
  await expect(page.getByTestId('position')).toHaveText(/^Turn 2 of 3 · Source · sentence 2 of 2$/)
  await page.keyboard.press('l')
  await page.keyboard.press('l')
  await expect(page.getByTestId('bead-row')).toHaveCount(4)
  await expect(current(page)).toHaveAttribute('data-bead-id', String(s2!.id))
  await expect(row(page, s1!.id)).toHaveCount(1)
})

test('reviewing a turn does not review its sentences; reviewing both sentences reviews the turn', async ({ page, request }) => {
  const { id, beads } = await importBook(request, 'Level marks')
  const [, s1, s2] = beads
  await open(page, id)
  await expect(page.getByTestId('book-progress')).toHaveText('Reviewed 0 / 3')
  await page.keyboard.press('ArrowDown')
  await page.keyboard.press('r')
  await expect(row(page, s1!.id)).toHaveAttribute('data-reviewed', 'true')
  await expect(page.getByTestId('book-progress')).toHaveText('Reviewed 1 / 3')
  await expect.poll(async () => (await getBook(request, id)).beads.map((b: Bead) => b.review_level)).toEqual([null, 'turn', 'turn', null])
  await page.goto('/')
  await expect(page.locator(`[data-book-id="${id}"]`)).toContainText('3 turns, 1 reviewed')
  await open(page, id)
  await level(page, 'sentence').click()
  await expect(page.getByTestId('book-progress')).toHaveText('Reviewed 0 / 4')
  for (const b of [s1!, s2!]) await expect(row(page, b.id)).toHaveAttribute('data-reviewed', 'false')
  // Review the two sentences at sentence level; then the turn, which was only reviewed at turn level, stays reviewed,
  // and clearing at turn level first shows the converse.
  await page.keyboard.press('ArrowDown')
  await page.keyboard.press('r')
  await expect(row(page, s1!.id)).toHaveAttribute('data-reviewed', 'true')
  await page.keyboard.press('ArrowDown')
  await page.keyboard.press('r')
  await expect(row(page, s2!.id)).toHaveAttribute('data-reviewed', 'true')
  await expect(page.getByTestId('book-progress')).toHaveText('Reviewed 2 / 4')
  await level(page, 'turn').click()
  await expect(row(page, s1!.id)).toHaveAttribute('data-reviewed', 'true')
  await expect(page.getByTestId('book-progress')).toHaveText('Reviewed 1 / 3')
})

test('both sentences reviewed at sentence level make the turn reviewed, one alone does not', async ({ page, request }) => {
  const { id, beads } = await importBook(request, 'Sentences to turn')
  const [, s1] = beads
  await open(page, id)
  await level(page, 'sentence').click()
  await page.keyboard.press('ArrowDown')
  await page.keyboard.press('r')
  await expect(row(page, s1!.id)).toHaveAttribute('data-reviewed', 'true')
  await level(page, 'turn').click()
  await expect(row(page, s1!.id)).toHaveAttribute('data-reviewed', 'false')
  await expect(page.getByTestId('book-progress')).toHaveText('Reviewed 0 / 3')
  await page.goto('/')
  await expect(page.locator(`[data-book-id="${id}"]`)).toContainText('3 turns, 0 reviewed')
  await open(page, id)
  await level(page, 'sentence').click()
  await page.keyboard.press('ArrowDown')
  await page.keyboard.press('ArrowDown')
  await page.keyboard.press('r')
  await level(page, 'turn').click()
  await expect(row(page, s1!.id)).toHaveAttribute('data-reviewed', 'true')
  await expect(page.getByTestId('book-progress')).toHaveText('Reviewed 1 / 3')
})

test('n goes to the next unit not reviewed at the level', async ({ page, request }) => {
  const { id, beads } = await importBook(request, 'Next unreviewed')
  const [n1, s1, , n2] = beads
  await open(page, id)
  await expect(current(page)).toHaveAttribute('data-bead-id', String(n1!.id))
  await page.keyboard.press('r')
  await expect(row(page, n1!.id)).toHaveAttribute('data-reviewed', 'true')
  await page.keyboard.press('n')
  await expect(current(page)).toHaveAttribute('data-bead-id', String(s1!.id))
  await page.keyboard.press('r')
  await expect(row(page, s1!.id)).toHaveAttribute('data-reviewed', 'true')
  await page.keyboard.press('n')
  await expect(current(page)).toHaveAttribute('data-bead-id', String(n2!.id))
  await page.keyboard.press('r')
  await expect(row(page, n2!.id)).toHaveAttribute('data-reviewed', 'true')
  await page.keyboard.press('n')
  await expect(page.getByTestId('status')).toHaveText('Every turn is reviewed')
})

// The beads as [source sentences, target sentences], in order, from the API.
async function shape(request: APIRequestContext, id: string) {
  const book = await getBook(request, id)
  return book.beads.map((b: { source: { text: string }[]; target: { text: string }[] }) => [
    b.source.map((s) => s.text),
    b.target.map((s) => s.text),
  ])
}

const N1 = 'Marie arriva dans la vallée.'
const S1 = '— Zorbe lunai tu vanet.'
const S2 = 'Il pleuvait sur la route.'
const N2 = 'Paul partit sans un mot.'
const T = ['Maria arrivò nella valle.', '— Zorba lunai tu vanet.', 'Pioveva sulla strada.', 'Paolo partì senza una parola.']
const ORIGINAL = [[[N1], [T[0]]], [[S1], [T[1]]], [[S2], [T[2]]], [[N2], [T[3]]]]

async function openAtSpeechTurn(page: Page, request: APIRequestContext, title: string) {
  const { id, beads } = await importBook(request, title)
  await open(page, id)
  await page.keyboard.press('ArrowDown')
  await expect(current(page)).toHaveAttribute('data-bead-id', String(beads[1]!.id))
  return { id, beads }
}

test('Alt+Down on a multi-bead turn moves its last sentence into the next unit; Ctrl+Z undoes it', async ({ page, request }) => {
  const { id } = await openAtSpeechTurn(page, request, 'Turn move next')
  await page.keyboard.press('Tab')
  await page.keyboard.press('Alt+ArrowDown')
  await expect.poll(() => shape(request, id)).toEqual([
    [[N1], [T[0]]], [[S1], [T[1]]], [[], [T[2]]], [[S2, N2], [T[3]]],
  ])
  await page.keyboard.press('Control+z')
  await expect.poll(() => shape(request, id)).toEqual(ORIGINAL)
})

test('Alt+Up on a multi-bead turn moves its first sentence into the previous unit; Ctrl+Z undoes it', async ({ page, request }) => {
  const { id } = await openAtSpeechTurn(page, request, 'Turn move previous')
  await page.keyboard.press('Alt+ArrowUp')
  await expect.poll(() => shape(request, id)).toEqual([
    [[N1, S1], [T[0]]], [[], [T[1]]], [[S2], [T[2]]], [[N2], [T[3]]],
  ])
  await page.keyboard.press('Control+z')
  await expect.poll(() => shape(request, id)).toEqual(ORIGINAL)
})

test('a move is refused when the unit edge bead has no sentence on the side', async ({ page, request }) => {
  const { id } = await openAtSpeechTurn(page, request, 'Turn move refused')
  await page.keyboard.press('ArrowRight')
  await page.keyboard.press('Tab')
  await page.keyboard.press('Alt+ArrowDown')
  await expect.poll(async () => (await shape(request, id))[2][1]).toEqual([])
  await page.keyboard.press('Alt+ArrowDown')
  await expect(page.getByTestId('status')).toHaveText("The turn's last bead has no target sentence: switch to sentences (L)")
})

test('M on a multi-bead turn merges its last bead with the next unit; Ctrl+Z undoes it', async ({ page, request }) => {
  const { id } = await openAtSpeechTurn(page, request, 'Turn merge')
  await page.keyboard.press('m')
  await expect.poll(() => shape(request, id)).toEqual([
    [[N1], [T[0]]], [[S1], [T[1]]], [[S2, N2], [T[2], T[3]]],
  ])
  await page.keyboard.press('Control+z')
  await expect.poll(() => shape(request, id)).toEqual(ORIGINAL)
})

test('S on a source sentence where a bead crosses a turn break splits there; Ctrl+Z undoes it', async ({ page, request }) => {
  const { id } = await openAtSpeechTurn(page, request, 'Turn split')
  await page.keyboard.press('m')
  await expect.poll(async () => (await shape(request, id)).length).toBe(3)
  await page.keyboard.press('Tab')
  await page.keyboard.press('Tab')
  await expect(page.getByTestId('position')).toHaveText(/sentence 3 of 3$/)
  await page.keyboard.press('s')
  await expect.poll(async () => (await shape(request, id)).length).toBe(4)
  expect(await shape(request, id)).toEqual([
    [[N1], [T[0]]], [[S1], [T[1]]], [[S2], [T[2], T[3]]], [[N2], []],
  ])
  await page.keyboard.press('Control+z')
  await expect.poll(async () => (await shape(request, id)).length).toBe(3)
})

test('S inside a speech paragraph, or on the target side, is refused', async ({ page, request }) => {
  const { id } = await openAtSpeechTurn(page, request, 'Turn split refused')
  // Sentence level: merge the two sentences of the speech paragraph into one bead.
  await page.keyboard.press('l')
  await page.keyboard.press('l')
  await expect(page.getByTestId('bead-row')).toHaveCount(4)
  await page.keyboard.press('m')
  await expect.poll(async () => (await shape(request, id)).length).toBe(3)
  await page.keyboard.press('l')
  await expect(level(page, 'turn')).toHaveAttribute('aria-pressed', 'true')
  await page.keyboard.press('Tab')
  await expect(page.getByTestId('position')).toHaveText(/sentence 2 of 2$/)
  await page.keyboard.press('s')
  await expect(page.getByTestId('status')).toHaveText(
    'A turn can be split only at a source break that a bead crosses: switch to sentences (L) to split here',
  )
  await page.keyboard.press('ArrowRight')
  await page.keyboard.press('Tab')
  await page.keyboard.press('s')
  await expect(page.getByTestId('status')).toHaveText(
    'A turn can be split only at a source break that a bead crosses: switch to sentences (L) to split here',
  )
  expect((await shape(request, id)).length).toBe(3)
})

test('a sentence cut at a unit edge and pasted at the neighbouring unit moves; Ctrl+Z undoes it', async ({ page, request }) => {
  const { id, beads } = await openAtSpeechTurn(page, request, 'Turn cut paste')
  await page.keyboard.press('Tab')
  await page.keyboard.press('Control+x')
  await page.keyboard.press('ArrowDown')
  await expect(current(page)).toHaveAttribute('data-bead-id', String(beads[3]!.id))
  await page.keyboard.press('Control+v')
  await expect.poll(() => shape(request, id)).toEqual([
    [[N1], [T[0]]], [[S1], [T[1]]], [[], [T[2]]], [[S2, N2], [T[3]]],
  ])
  await page.keyboard.press('Control+z')
  await expect.poll(() => shape(request, id)).toEqual(ORIGINAL)
  // The other way: the next unit's first sentence into the turn.
  await page.keyboard.press('Control+x')
  await page.keyboard.press('ArrowUp')
  await page.keyboard.press('Control+v')
  await expect.poll(() => shape(request, id)).toEqual([
    [[N1], [T[0]]], [[S1], [T[1]]], [[S2, N2], [T[2]]], [[], [T[3]]],
  ])
  await page.keyboard.press('Control+z')
  await expect.poll(() => shape(request, id)).toEqual(ORIGINAL)
})

test('editing a sentence inside a multi-bead turn still works', async ({ page, request }) => {
  const { id } = await openAtSpeechTurn(page, request, 'Turn edit')
  await page.keyboard.press('Tab')
  await page.keyboard.press('Enter')
  const editor = page.getByTestId('segment-editor')
  await expect(editor).toHaveValue(S2)
  await editor.fill('Il pleuvait sur le chemin.')
  await page.keyboard.press('Enter')
  await expect.poll(async () => (await getBook(request, id)).beads[2].source[0].text).toBe('Il pleuvait sur le chemin.')
  expect((await getBook(request, id)).beads).toHaveLength(4)
})
