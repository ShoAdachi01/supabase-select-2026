import { test, expect } from '@playwright/test';

test('discover, review, reuse feedback, approve permission, and export evidence', async ({
  page,
}) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Explore the Orbit demo' }).click();
  await expect(page.getByText('6 candidate appearances found')).toBeVisible();
  await expect(page.locator('.finding-card')).toHaveCount(5);
  await page.getByRole('button', { name: /Blue bunny plush/ }).click();
  const drawer = page.getByRole('dialog', { name: 'Review appearance' });
  await drawer
    .getByPlaceholder('What did you verify? What still needs investigation?')
    .fill('Different character: blue rabbit, not Orbit.');
  await drawer.getByRole('button', { name: 'Not a match', exact: true }).click();
  await expect(drawer.getByText(/Last owner decision: Not a match/)).toBeVisible();
  await drawer.getByRole('button', { name: 'Close review' }).click();
  await page.getByRole('button', { name: 'Find appearances', exact: true }).click();
  await expect(page.getByText(/1 identical-image correction/)).toBeVisible();
  await page.getByRole('button', { name: 'Dismissed', exact: true }).click();
  await expect(page.locator('.finding-card')).toHaveCount(1);
  await expect(page.getByText('Owner-rejected match', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'All appearances', exact: false }).click();
  await page
    .getByRole('button', { name: /Space cat graphic T-shirt/ })
    .first()
    .click();
  const download = page.waitForEvent('download');
  await drawer.getByRole('button', { name: 'Export evidence bundle' }).click();
  expect((await download).suggestedFilename()).toMatch(/^trace-evidence-.*\.zip$/);
  await drawer.getByRole('button', { name: 'Close review' }).click();
  await page.getByRole('button', { name: 'Licensing', exact: false }).first().click();
  await page.getByRole('button', { name: 'New request', exact: true }).click();
  const form = page.getByRole('dialog', { name: 'Record a licensing request' });
  await form.getByLabel('Applicant / company').fill('Moon Market');
  await form.getByLabel('Applicant website domain').fill('moon-market.example');
  await form.getByLabel('Product category').fill('apparel');
  await form.getByLabel('Territory').fill('US');
  await form.getByLabel('Ends on').fill('2027-12-31');
  await form.getByRole('button', { name: 'Record request', exact: true }).click();
  await expect(page.getByText('Moon Market', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Record approval', exact: true }).click();
  await expect(page.getByText('approved', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Discovery', exact: false }).first().click();
  await page.getByRole('button', { name: 'Authorized', exact: true }).click();
  await expect(page.locator('.finding-card')).toHaveCount(2);
  await page.reload();
  await expect(page.getByText('Characters in your library')).toBeVisible();
  await expect(page.locator('.stat').first().getByText('01')).toBeVisible();
});

test('upload reference artwork and inspect live MCP schemas', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Add character', exact: true }).first().click();
  const form = page.getByRole('dialog', { name: 'Add a character' });
  await form.getByLabel('Character name').fill('My Orbit');
  await form.getByLabel('Alternate names').fill('space cat, orbital cat');
  await form.locator('input[type=file]').setInputFiles('public/demo/reference.png');
  await form.getByRole('button', { name: 'Add character', exact: true }).click();
  await expect(page.getByText('1 reference image · 2 alternate names')).toBeVisible();
  await page.getByRole('button', { name: 'Agent tools', exact: true }).click();
  await page.getByRole('button', { name: 'Inspect live tool schemas' }).click();
  await expect(page.locator('.schema-result')).toContainText('find_character_usage');
  await expect(page.locator('.schema-result')).toContainText('prepare_evidence');
});

test('mobile discovery and review do not overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await page.getByRole('button', { name: 'Explore the Orbit demo' }).click();
  await expect(page.getByText('6 candidate appearances found')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.getByRole('button', { name: /Blue bunny plush/ }).click();
  await expect(page.getByRole('dialog', { name: 'Review appearance' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});
