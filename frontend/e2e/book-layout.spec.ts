import { test, expect } from '@playwright/test'

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
})
