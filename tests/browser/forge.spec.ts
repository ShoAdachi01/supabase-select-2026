import { expect, test } from '@playwright/test';

test('creates a skill, predicts, saves feedback, and discovers it over MCP', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByText('Supabase connected')).toBeVisible();
  await page.screenshot({ path: 'test-results/library.png', fullPage: true });
  await page.getByRole('button', { name: 'Will this shipment be late?' }).click();
  await expect(page.getByText('Post-outcome field: possible target leakage')).toBeVisible();
  await expect(page.getByRole('checkbox').last()).not.toBeChecked();
  await page.screenshot({ path: 'test-results/task.png', fullPage: true });
  await page.getByRole('button', { name: 'Train & evaluate' }).click();
  await expect(
    page.getByRole('heading', { name: 'Your agent just learned a new skill.' }),
  ).toBeVisible({ timeout: 45000 });
  await page.screenshot({ path: 'test-results/results.png', fullPage: true });
  await page.getByRole('button', { name: 'Use this skill' }).click();
  await page.getByRole('button', { name: 'Run prediction' }).click();
  await expect(page.getByText('0 LLM tokens')).toBeVisible();
  await page.getByLabel('Actual outcome', { exact: true }).selectOption('delayed');
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Saved', exact: true })).toBeVisible();
  await page.screenshot({ path: 'test-results/prediction.png', fullPage: true });
  await page.getByRole('button', { name: 'Agent connection', exact: true }).click();
  await page.getByRole('button', { name: 'Test connection' }).click();
  await expect(page.getByRole('status')).toContainText('ready tool');
  await page.getByRole('button', { name: 'Skill library', exact: false }).click();
  await expect(page.getByRole('button', { name: /Predict delayed/ })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('button', { name: /Predict delayed/ })).toBeVisible();
});

test('supports mobile layout without horizontal page overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Give your agent a new skill.' })).toBeVisible();
  const hasOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth,
  );
  expect(hasOverflow).toBe(false);
  await page.screenshot({ path: 'test-results/mobile.png', fullPage: true });
});

test('uploads a CSV and evaluates future rows with a chronological regression split', async ({
  page,
}) => {
  const rows = Array.from({ length: 150 }, (_, i) => {
    const day = new Date(Date.UTC(2025, 0, i + 1)).toISOString().slice(0, 10);
    const temperature = 15 + Math.sin(i * 0.6) * 8;
    return `${day},${temperature},${(100 + temperature * 4 + Math.cos(i) * 2).toFixed(3)}`;
  });
  await page.goto('/');
  await expect(page.getByText('Supabase connected')).toBeVisible();
  await page.getByRole('button', { name: 'Create a skill', exact: true }).first().click();
  await page.locator('input[type="file"]').setInputFiles({
    name: 'building-demand.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from(['date,temperature,demand', ...rows].join('\n')),
  });
  await expect(page.getByLabel('Outcome column')).toHaveValue('demand');
  await page.getByLabel('Evaluation split').selectOption('temporal');
  await page.getByLabel('Time column').selectOption('date');
  await page.getByRole('button', { name: 'Train & evaluate' }).click();
  await expect(page.getByRole('button', { name: 'Use this skill' })).toBeVisible({
    timeout: 45000,
  });
  await expect(page.getByText('FINAL TEST MEAN ABSOLUTE ERROR')).toBeVisible();
  await page.getByRole('button', { name: 'Use this skill' }).click();
  await page.getByRole('button', { name: 'Run prediction' }).click();
  await expect(page.getByText('0 LLM tokens')).toBeVisible();
  await page.getByLabel('Actual outcome', { exact: true }).fill('150');
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Saved', exact: true })).toBeVisible();
});
