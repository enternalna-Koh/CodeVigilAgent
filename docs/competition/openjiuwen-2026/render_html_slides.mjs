/**
 * Render slides.html -> PNG per .slide, then python builds PPTX.
 */
import { chromium } from 'playwright';
import path from 'path';
import { fileURLToPath, pathToFileURL } from 'url';
import fs from 'fs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const htmlPath = path.join(__dirname, 'slides.html');
const outDir = path.join(__dirname, 'assets', 'html-slides');

fs.mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({
  viewport: { width: 1920, height: 1080 },
  deviceScaleFactor: 1,
});

await page.goto(pathToFileURL(htmlPath).href, { waitUntil: 'networkidle' });
// ensure images loaded
await page.waitForTimeout(800);

const slides = page.locator('.slide');
const n = await slides.count();
const files = [];
for (let i = 0; i < n; i++) {
  const slide = slides.nth(i);
  const name = (await slide.getAttribute('data-name')) || `slide-${String(i + 1).padStart(2, '0')}`;
  const out = path.join(outDir, `${String(i + 1).padStart(2, '0')}-${name}.png`);
  await slide.screenshot({ path: out, type: 'png' });
  files.push(out);
  console.log('shot', out);
}

await browser.close();
fs.writeFileSync(path.join(outDir, 'manifest.json'), JSON.stringify({ files }, null, 2));
console.log('done', n, 'slides');
