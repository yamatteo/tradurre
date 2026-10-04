import { test, expect } from '@playwright/test'
import { SHORTCUTS } from '../src/keys'

// The book screen's bars (PLAN.md, "Layout: toolbars and import log"), at the smallest laptop size SPEC §4 targets.
test('at 1366 × 768 the two bars fit and have their heights; the import log opens and closes', async ({ page, request }) => {
  await page.setViewportSize({ width: 1366, height: 768 })
  const res = await request.post('/api/v2/books', {
    multipart: {
      source: { name: 'fr.txt', mimeType: 'text/plain', buffer: Buffer.from('Marie arriva.\n\nPaul partit.') },
      target: { name: 'it.txt', mimeType: 'text/plain', buffer: Buffer.from('Marie arrivò.\n\nPaul partì.', 'latin1') },
      title: 'Bars',
    },
  })
  expect(res.status()).toBe(201)
  await page.goto(`/book/${(await res.json()).id}`)
  await expect(page.locator('[data-testid="bead-row"][data-current="true"]')).toBeVisible()

  for (const [id, height] of [['top-bar', 40], ['second-bar', 38]] as const) {
    const bar = page.getByTestId(id)
    expect((await bar.boundingBox())!.height).toBe(height)
    const fits = await bar.evaluate((el) => el.scrollWidth <= el.clientWidth)
    expect(fits, `${id} overflows`).toBe(true)
  }

  const button = page.getByTestId('import-log')
  await button.click()
  await expect(page.getByTestId('import-log-panel')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByTestId('import-log-panel')).toHaveCount(0)
  await button.click()
  await page.getByTestId('import-log-panel').getByRole('button', { name: 'Close' }).click()
  await expect(page.getByTestId('import-log-panel')).toHaveCount(0)
  await button.click()
  await button.click()
  await expect(page.getByTestId('import-log-panel')).toHaveCount(0)
  await button.click()
  await expect(page.getByTestId('import-log-panel')).toBeVisible()
  await page.getByTestId('bead-row').last().click()  // a click outside closes it
  await expect(page.getByTestId('import-log-panel')).toHaveCount(0)
})

test('h and the Keys button open the shortcuts panel; it lists every shortcut, holds the keys, and Esc closes it', async ({ page, request }) => {
  const res = await request.post('/api/v2/books', {
    multipart: {
      source: { name: 'fr.txt', mimeType: 'text/plain', buffer: Buffer.from('Marie arriva.\n\nPaul partit.') },
      target: { name: 'it.txt', mimeType: 'text/plain', buffer: Buffer.from('Marie arrivò.\n\nPaul partì.') },
      title: 'Keys',
    },
  })
  expect(res.status()).toBe(201)
  await page.goto(`/book/${(await res.json()).id}`)
  const current = page.locator('[data-testid="bead-row"][data-current="true"]')
  const first = await current.getAttribute('data-bead-id')
  const panel = page.getByTestId('keys-panel')

  await page.keyboard.press('h')
  await expect(panel).toBeVisible()
  await expect(panel).toHaveAttribute('role', 'dialog')
  await expect(panel.getByTestId('shortcut')).toHaveCount(SHORTCUTS.length)
  for (const s of SHORTCUTS) await expect(panel.locator(`[data-shortcut="${s.id}"]`)).toContainText(s.label)
  await page.keyboard.press('ArrowDown')
  await page.keyboard.press('r')
  await page.keyboard.press('Escape')
  await expect(panel).toHaveCount(0)
  await expect(current).toHaveAttribute('data-bead-id', first!)
  await expect(current).toHaveAttribute('data-reviewed', 'false')

  await page.getByTestId('keys').click()
  await expect(panel).toBeVisible()
  await page.mouse.click(5, 5)  // the scrim
  await expect(panel).toHaveCount(0)
  await page.getByTestId('keys').click()
  await panel.getByRole('button', { name: /Close/ }).click()
  await expect(panel).toHaveCount(0)
})

test('More → Target text (.txt) downloads the target edition, named after the book', async ({ page, request }) => {
  const res = await request.post('/api/v2/books', {
    multipart: {
      source: { name: 'fr.txt', mimeType: 'text/plain', buffer: Buffer.from('Marie arriva.\n\nPaul partit.') },
      target: { name: 'it.txt', mimeType: 'text/plain', buffer: Buffer.from('Maria arrivò.\n\nPaolo partì.') },
      title: 'Edition',
      source_lang: 'fr',
      target_lang: 'it',
    },
  })
  expect(res.status()).toBe(201)
  await page.goto(`/book/${(await res.json()).id}`)
  await expect(page.locator('[data-testid="bead-row"][data-current="true"]')).toBeVisible()

  await page.getByTestId('more').click()
  const downloaded = page.waitForEvent('download')
  await page.getByTestId('export-target-txt').click()
  const download = await downloaded
  expect(download.suggestedFilename()).toBe('Edition (IT).txt')
  const text = (await download.createReadStream()).setEncoding('utf8')
  let content = ''
  for await (const chunk of text) content += chunk
  expect(content).toBe('﻿Maria arrivò.\n\nPaolo partì.\n')
  await expect(page.getByTestId('more-menu')).toHaveCount(0)
})
