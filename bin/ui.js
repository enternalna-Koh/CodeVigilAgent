/**
 * ReviewAgent terminal UI — spreading splash + nupu companion.
 */
const os = require('os');
const path = require('path');
const fs = require('fs');
const { chalk, c, sleep } = require('./ui-colors');

let boxen, ora;
try {
  boxen = require('boxen');
  ora = require('ora');
} catch {
  boxen = (s) => s;
  ora = () => ({ start() { return this; }, succeed() {}, fail() {}, stop() {} });
}

const { interactPet, ensureHatched, animateIdle, renderFace } = require('./buddy');

/** Raw logo rows (no color) for column-spread reveal. */
const LOGO_ROWS = [
  '  ██████╗ ███████╗██╗   ██╗██╗███████╗██╗    ██╗',
  '  ██╔══██╗██╔════╝██║   ██║██║██╔════╝██║    ██║',
  '  ██████╔╝█████╗  ██║   ██║██║█████╗  ██║ █╗ ██║',
  '  ██╔══██╗██╔══╝  ╚██╗ ██╔╝██║██╔══╝  ██║███╗██║',
  '  ██║  ██║███████╗ ╚████╔╝ ██║███████╗╚███╔███╔╝',
  '  ╚═╝  ╚═╝╚══════╝  ╚═══╝  ╚═╝╚══════╝ ╚══╝╚══╝',
];

const TAGLINE = '            ✦  A G E N T  · Ascend AI Infra';

function homeDir() {
  return process.env.REVIEWAGENT_HOME || path.join(os.homedir(), '.reviewagent');
}

function configPath() {
  return path.join(homeDir(), 'ai_config.json');
}

function readConfig() {
  const p = configPath();
  if (!fs.existsSync(p)) return null;
  try {
    return JSON.parse(fs.readFileSync(p, 'utf8'));
  } catch {
    return null;
  }
}

function hasUsableApiKey(cfg) {
  if (process.env.OPENAI_API_KEY || process.env.AI_API_KEY || process.env.ANTHROPIC_API_KEY) {
    return true;
  }
  if (!cfg || !cfg.api_key) return false;
  const key = String(cfg.api_key).trim();
  return key && key !== 'YOUR_API_KEY_HERE';
}

async function typeLine(text, delay = 12) {
  for (const ch of text) {
    process.stdout.write(ch);
    // eslint-disable-next-line no-await-in-loop
    await sleep(delay);
  }
  process.stdout.write('\n');
}

/**
 * Spread/reveal logo left → right with a soft glowing edge (蔓延感).
 */
async function revealLogoSpread({ stepMs = 22 } = {}) {
  const rows = LOGO_ROWS;
  const width = Math.max(...rows.map((r) => r.length));
  const height = rows.length;

  for (let i = 0; i < height; i += 1) process.stdout.write('\n');

  const edge = 4; // glowing front width
  for (let col = 0; col <= width + edge; col += 1) {
    process.stdout.write(`\x1b[${height}A`);
    for (let y = 0; y < height; y += 1) {
      // diagonal lag: lower rows trail slightly → wave
      const lag = Math.floor(y * 1.4);
      const front = col - lag;
      const line = rows[y];
      let out = '';
      for (let x = 0; x < line.length; x += 1) {
        const ch = line[x];
        if (ch === ' ') {
          out += ' ';
          continue;
        }
        if (x < front - edge) {
          out += c.brand(ch);
        } else if (x < front) {
          // wave edge: brighter teal → sakura
          const t = (front - x) / edge;
          out += t > 0.5 ? c.glow(ch) : c.accent(ch);
        } else {
          out += ' ';
        }
      }
      process.stdout.write(`${out}\n`);
    }
    // eslint-disable-next-line no-await-in-loop
    await sleep(stepMs);
  }

  // tagline types in after the spread
  await typeLine(c.accent('            ✦  A G E N T') + c.mute(' · Ascend AI Infra'), 8);
}

async function bootSpark() {
  const sparks = ['·', '✦', '✧', '✦', '·'];
  for (const s of sparks) {
    process.stdout.write(`\r  ${c.accent(s)} ${c.mute('nupu 正在铺开画面…')}  `);
    // eslint-disable-next-line no-await-in-loop
    await sleep(90);
  }
  process.stdout.write(`\r${' '.repeat(36)}\r`);
}

/**
 * Full splash: spark → spreading logo → pet walk → optional interact.
 */
async function splash({ firstRun = false, withPet = true } = {}) {
  const petOn =
    withPet &&
    process.env.REVIEWAGENT_NO_PET !== '1' &&
    process.env.REVIEWAGENT_FAST !== '1';

  console.clear?.();
  await bootSpark();
  await revealLogoSpread({ stepMs: firstRun ? 28 : 20 });
  console.log('');

  if (petOn) {
    // Claude Code /buddy–style: hatch card + idle tick + optional interact
    if (firstRun) {
      await interactPet({ force: true });
    } else {
      const { buddy } = ensureHatched();
      const face = renderFace(buddy);
      console.log(
        `  ${c.accent(buddy.name)} ${c.mute(face)}  ${c.mute(`${buddy.species} · ${buddy.rarity}`)}`,
      );
      await animateIdle(buddy, {
        ticks: 6,
        delay: 400,
        bubble: '坐在输入框旁边看着你…',
      });
      console.log(c.mute('  互动: reviewagent buddy   ·   换种子: REVIEWAGENT_BUDDY_SEED\n'));
    }
  }

  const body = firstRun
    ? `${c.accent('✦ 第一次见面')}  ·  接下来会引导你配置 API\n` +
      `${c.mute('昇腾算子 / 推理 / CANN · 兼容 cc-switch')}`
    : `${c.ok('●')} ${c.ink('就绪')}  ${c.mute('问题或 PR/Issue URL · /help · /exit')}\n` +
      `${c.mute('review · search · config · doctor · model')}`;

  console.log(
    boxen(body, {
      padding: { top: 0, bottom: 0, left: 1, right: 1 },
      margin: { top: 0, bottom: 1, left: 1, right: 1 },
      borderStyle: 'round',
      borderColor: firstRun ? 'magenta' : 'cyan',
      dimBorder: true,
    }),
  );
}

function spinner(text) {
  return ora({ text: c.mute(text), color: 'cyan', spinner: 'dots' });
}

const LOGO = LOGO_ROWS.map((r) => c.brand(r)).join('\n') + `\n${c.accent(TAGLINE)}`;

module.exports = {
  c,
  LOGO,
  LOGO_ROWS,
  homeDir,
  configPath,
  readConfig,
  hasUsableApiKey,
  splash,
  revealLogoSpread,
  spinner,
  typeLine,
  sleep,
  chalk,
  boxen,
};
