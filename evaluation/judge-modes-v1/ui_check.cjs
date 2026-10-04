/* Render the retained local report only. No model calls or scene mutation. */
const { chromium } = require(process.env.HARNESS_PLAYWRIGHT_MODULE || 'playwright');
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');
(async () => {
  const root = path.resolve(process.argv[2]);
  const plan = JSON.parse(fs.readFileSync(path.join(root, 'plan.json'), 'utf8'));
  const files = ['index.html', ...plan.map(j => `runs/${j.id}/evaluation/report.html`)];
  const browser = await chromium.launch({ headless: true, ...(process.env.HARNESS_CHROME ? { executablePath: process.env.HARNESS_CHROME } : {}) });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(String(error)));
  const checks = [];
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
    for (const file of files) {
      await page.goto(pathToFileURL(path.join(root, file)).href);
      const readback = await page.evaluate(() => ({
        title: document.querySelector('h1')?.textContent,
        width: document.documentElement.scrollWidth,
        viewport: innerWidth,
        images: Array.from(document.images).map(i => ({ loaded: i.complete && i.naturalWidth > 0, alt: i.alt })),
      }));
      if (!readback.title || readback.width > readback.viewport || readback.images.some(i => !i.loaded || !i.alt)) {
        throw Error(`${file}: ${JSON.stringify(readback)}`);
      }
      checks.push({ file, width, images: readback.images.length, overflow: false });
      if (file === 'index.html') await page.screenshot({ path: path.join(root, `report-${width}.png`) });
      if (file.includes('/gantry-detailed-02/evaluation/')) await page.screenshot({ path: path.join(root, `scene-report-${width}.png`) });
    }
  }
  await browser.close();
  if (errors.length) throw Error(errors.join('\n'));
  const result = { pages: files.length, viewport_checks: checks.length, widths: [1440, 390], errors, checks };
  fs.writeFileSync(path.join(root, 'ui-verification.json'), JSON.stringify(result, null, 2) + '\n');
  process.stdout.write(JSON.stringify({ pages: result.pages, viewport_checks: result.viewport_checks, errors }) + '\n');
})().catch(error => { process.stderr.write(String(error) + '\n'); process.exitCode = 1; });
