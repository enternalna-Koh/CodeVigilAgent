/**
 * ReviewAgent Buddy — Claude Code /buddy–style terminal companion.
 *
 * Mechanics mirror CC: deterministic bones from seed, rarity gacha,
 * 3-frame ASCII sprites + blink, hat slot, idle cycle, speech bubble,
 * pet hearts, hatch card. Sprites are original (Ascend-flavored), not
 * Anthropic assets.
 */
const fs = require('fs');
const os = require('os');
const path = require('path');
const { c, sleep, chalk } = require('./ui-colors');

let boxen;
try {
  boxen = require('boxen');
} catch {
  boxen = (s) => s;
}

let inquirer;
try {
  inquirer = require('inquirer');
} catch {
  inquirer = null;
}

const SPECIES = [
  'duck', 'fox', 'blob', 'cat', 'dragon', 'owl', 'penguin', 'turtle',
  'ghost', 'rabbit', 'robot', 'mushroom', 'chip', 'crane', 'panda',
  'axolotl', 'cloud', 'tensor',
];

const EYES = ['·', '✦', '×', '◉', '@', '°'];
const HATS = ['none', 'crown', 'tophat', 'propeller', 'halo', 'wizard', 'beanie', 'tinyduck'];
const RARITIES = ['common', 'uncommon', 'rare', 'epic', 'legendary'];
const RARITY_WEIGHTS = { common: 60, uncommon: 25, rare: 10, epic: 4, legendary: 1 };
const RARITY_STARS = {
  common: '★',
  uncommon: '★★',
  rare: '★★★',
  epic: '★★★★',
  legendary: '★★★★★',
};
const STAT_NAMES = ['DEBUGGING', 'PATIENCE', 'CHAOS', 'WISDOM', 'SNARK'];

/** Idle tick sequence (same rhythm as CC buddy): mostly rest, rare fidget/blink. */
const IDLE_CYCLE = [0, 0, 0, 0, 1, 0, 0, 0, -1, 0, 0, 2, 0, 0, 0];

const HAT_LINES = {
  none: '            ',
  crown: '    └┬┘     ',
  tophat: '    ┌─┐     ',
  propeller: '    ─⊙─     ',
  halo: '    ︵︵     ',
  wizard: '    /\\/     ',
  beanie: '    ∩∩      ',
  tinyduck: '    (>·     ',
};

const RARITY_COLOR = {
  common: (s) => c.mute(s),
  uncommon: (s) => c.ok(s),
  rare: (s) => c.brand(s),
  epic: (s) => c.accent(s),
  legendary: (s) => (chalk.hex ? chalk.hex('#F5C542')(s) : c.warn(s)),
};

/**
 * Bodies: line0 = hat slot (blank), then 4 body lines. {E} → eye char.
 * 3 frames each for idle fidget. Original art — Ascend / cute CLI style.
 */
const BODIES = {
  duck: [
    ['            ', '     __     ', '   <({E} )___ ', '    (  ._>  ', '     `--´   '],
    ['            ', '     __     ', '   <({E} )___ ', '    (  ._>  ', '     `--´~  '],
    ['            ', '     __     ', '   <({E} )___ ', '    (  .__> ', '     `--´   '],
  ],
  fox: [
    ['            ', '    /\\_/\\   ', '   ( {E}{E} )  ', '   /|   |\\  ', '    U   U   '],
    ['            ', '    /\\_/\\   ', '   ( {E}{E} )  ', '   /| ~ |\\  ', '    U   U   '],
    ['            ', '    /\\_/\\   ', '   ( - - )  ', '   /|   |\\  ', '    U   U   '],
  ],
  blob: [
    ['            ', '   .----.   ', '  ( {E}  {E} )  ', '  (      )  ', '   `----´   '],
    ['            ', '  .------.  ', '  ( {E}  {E} )  ', '  (      )  ', '   `------´ '],
    ['            ', '    .--.    ', '   ({E}  {E})   ', '   (    )   ', '    `--´    '],
  ],
  cat: [
    ['            ', '    /\\_/\\   ', '   ( {E} {E})  ', '   (  ω  )  ', '   (")_(")  '],
    ['            ', '    /\\_/\\   ', '   ( {E} {E})  ', '   (  ω  )~ ', '   (")_(")  '],
    ['            ', '    /\\_/\\   ', '   ( - -)   ', '   (  ω  )  ', '   (")_(")  '],
  ],
  dragon: [
    ['            ', '   /^\\ /^\\  ', '  < {E}  {E} >  ', '  (  ~~  )  ', '   `-vv-´   '],
    ['            ', '   /^\\ /^\\  ', '  < {E}  {E} >  ', '  (  ~~  )~ ', '   `-vv-´   '],
    ['            ', '   /^\\ /^\\  ', '  < -  - >  ', '  (  ~~  )  ', '   `-vv-´   '],
  ],
  owl: [
    ['            ', '   /\\  /\\   ', '  (({E})({E}))  ', '  (  ><  )  ', '   `----´   '],
    ['            ', '   /\\  /\\   ', '  (({E})({E}))  ', '  (  ><  )~ ', '   `----´   '],
    ['            ', '   /\\  /\\   ', '  ((-)(-))  ', '  (  ><  )  ', '   `----´   '],
  ],
  penguin: [
    ['            ', '    .---.   ', '   ({E}>{E})    ', '  /(   )\\   ', '   `---´    '],
    ['            ', '    .---.   ', '   ({E}>{E})    ', '  /( ~ )\\   ', '   `---´    '],
    ['            ', '    .---.   ', '   (- >-)   ', '  /(   )\\   ', '   `---´    '],
  ],
  turtle: [
    ['            ', '   _,--._   ', '  ( {E}  {E} )  ', ' /[______]\\ ', '  ``    ``  '],
    ['            ', '   _,--._   ', '  ( {E}  {E} )  ', ' /[__~~__]\\ ', '  ``    ``  '],
    ['            ', '   _,--._   ', '  ( -  - )  ', ' /[______]\\ ', '  ``    ``  '],
  ],
  ghost: [
    ['            ', '   .----.   ', '  / {E}  {E} \\  ', '  |      |  ', '  ~`~``~`~  '],
    ['            ', '   .----.   ', '  / {E}  {E} \\  ', '  |  ~~  |  ', '  ~~`~`~~`  '],
    ['            ', '   .----.   ', '  / -  - \\  ', '  |      |  ', '  ~`~``~`~  '],
  ],
  rabbit: [
    ['            ', '   (\\__/)   ', '  ( {E}  {E} )  ', ' =(  ..  )= ', '  (")__(")  '],
    ['            ', '   (\\__/)   ', '  ( {E}  {E} )  ', ' =(  ..  )=~', '  (")__(")  '],
    ['            ', '   (\\__/)   ', '  ( -  - )  ', ' =(  ..  )= ', '  (")__(")  '],
  ],
  robot: [
    ['            ', '   .[||].   ', '  [ {E}  {E} ]  ', '  [ ==== ]  ', '   `----´   '],
    ['            ', '   .[||].   ', '  [ {E}  {E} ]  ', '  [ =##= ]  ', '   `----´   '],
    ['            ', '   .[||].   ', '  [ -  - ]  ', '  [ ==== ]  ', '   `----´   '],
  ],
  mushroom: [
    ['            ', '   . o  .   ', ' .-o-OO-o-. ', ' (________) ', '  |{E}  {E}|    '],
    ['            ', '   . o  .   ', ' .-o-OO-o-. ', ' (___~~___) ', '  |{E}  {E}|    '],
    ['            ', '   . o  .   ', ' .-o-OO-o-. ', ' (________) ', '  |-  -|    '],
  ],
  chip: [
    ['            ', '  .======.  ', '  | {E}  {E} |  ', '  | NPU  |  ', '  `======´  '],
    ['            ', '  .======.  ', '  | {E}  {E} |  ', '  | N*U  |  ', '  `======´  '],
    ['            ', '  .======.  ', '  | -  - |  ', '  | NPU  |  ', '  `======´  '],
  ],
  crane: [
    ['            ', '     /^\\    ', '    ({E}>     ', '   /||\\     ', '  ~~||~~    '],
    ['            ', '     /^\\    ', '    ({E}>~    ', '   /||\\     ', '  ~~||~~    '],
    ['            ', '     /^\\    ', '    (- >    ', '   /||\\     ', '  ~~||~~    '],
  ],
  panda: [
    ['            ', '   /\\__/\\   ', '  ( {E}  {E})  ', '  (  ▽  )   ', '   `--´´    '],
    ['            ', '   /\\__/\\   ', '  ( {E}  {E})  ', '  (  ▽  )~  ', '   `--´´    '],
    ['            ', '   /\\__/\\   ', '  ( -  -)   ', '  (  ▽  )   ', '   `--´´    '],
  ],
  axolotl: [
    ['            ', '   \\^^^/    ', ' }~(____)~{ ', ' }~({E}..{E})~{ ', '   (_/\\_)   '],
    ['            ', '   \\^^^/    ', ' }~(____)~{ ', ' }~({E}..{E})~{ ', '   (_~~_)   '],
    ['            ', '   \\^^^/    ', ' }~(____)~{ ', ' }~(-..-)~{ ', '   (_/\\_)   '],
  ],
  cloud: [
    ['            ', '   ((   ))  ', '  (( {E}{E} ))  ', '   ((___))  ', '    ~~~~~   '],
    ['            ', '  (((   ))) ', '  (( {E}{E} ))  ', '   ((___))  ', '   ~~~~~~~  '],
    ['            ', '   ((   ))  ', '  (( -- ))  ', '   ((___))  ', '    ~~~~~   '],
  ],
  tensor: [
    ['            ', '   /||||\\   ', '  | {E}  {E} |  ', '  | rank |  ', '   \\||||/   '],
    ['            ', '   /||||\\   ', '  | {E}  {E} |  ', '  | r*nk |  ', '   \\||||/   '],
    ['            ', '   /||||\\   ', '  | -  - |  ', '  | rank |  ', '   \\||||/   '],
  ],
};

const NAME_POOL = [
  '昇芯', 'Nupu', '比特', '算子酱', 'Tensor', '小昇', 'Kernel', '闪闪',
  'DaVinci', 'Atlas', 'Pip', 'Mochi', 'Pixel', 'Nova', '芝麻', '豆包仔',
  'Claude旁', 'Ink', 'Glyph', '气泡',
];

const PERSONALITY_POOL = [
  '安静盯着你审 diff，偶尔点头。',
  '一看到 HCCL 就兴奋地蹦。',
  '毒舌但准：会说「这段 kernel 可以更短」。',
  '喜欢数 token，讨厌没跑的单测。',
  '对精度误差零容忍，对你很宽容。',
  '睡在 profiling 火焰图旁边取暖。',
  '信奉「先对齐再谈性能」。',
  '会在你写 commit message 时打哈欠。',
];

const BUBBLES = {
  greet: ['嗨，又见面啦', '准备审昇腾代码？', '我坐这儿看着', 'boop.', '加油，我盯着'],
  pet: ['♥ 舒服…', '再摸一下', '呜呜', '别停', '★ shiny mood'],
  feed: ['嚼嚼…算子饼干', '多谢投喂', '能量 +1', 'nom'],
  hatch: ['破壳啦！', '终于见到你', '我们绑定了', 'watch you work'],
  idle: ['…', '嗯', '继续', 'zZz', '👀'],
};

function buddyHome() {
  return process.env.REVIEWAGENT_HOME || path.join(os.homedir(), '.reviewagent');
}

function buddyPath() {
  return path.join(buddyHome(), 'buddy.json');
}

function seedId() {
  if (process.env.REVIEWAGENT_BUDDY_SEED) return String(process.env.REVIEWAGENT_BUDDY_SEED);
  try {
    return `${os.userInfo().username}@${os.hostname()}`;
  } catch {
    return `reviewagent@${os.hostname()}`;
  }
}

function fnv1a(str) {
  let h = 0x811c9dc5;
  const s = `${str}|reviewagent-buddy-2026`;
  for (let i = 0; i < s.length; i += 1) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

function mulberry32(a) {
  return function next() {
    let t = (a += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function pickWeighted(rng, weights) {
  const total = Object.values(weights).reduce((a, b) => a + b, 0);
  let r = rng() * total;
  for (const [k, w] of Object.entries(weights)) {
    r -= w;
    if (r <= 0) return k;
  }
  return Object.keys(weights)[0];
}

function rollBones(seed = seedId()) {
  const rng = mulberry32(fnv1a(seed));
  const rarity = pickWeighted(rng, RARITY_WEIGHTS);
  const species = SPECIES[Math.floor(rng() * SPECIES.length)];
  const eye = EYES[Math.floor(rng() * EYES.length)];
  const hatPool = rarity === 'common' ? HATS.slice(0, 3) : HATS;
  const hat = hatPool[Math.floor(rng() * hatPool.length)];
  const shiny = rng() < (rarity === 'legendary' ? 0.08 : 0.01);

  const stats = {};
  const peak = STAT_NAMES[Math.floor(rng() * STAT_NAMES.length)];
  const dump = STAT_NAMES.filter((s) => s !== peak)[Math.floor(rng() * 4)];
  const floor = { common: 20, uncommon: 30, rare: 40, epic: 50, legendary: 60 }[rarity];
  for (const name of STAT_NAMES) {
    let v = floor + Math.floor(rng() * (100 - floor));
    if (name === peak) v = Math.min(100, v + 20);
    if (name === dump) v = Math.max(5, v - 25);
    stats[name] = v;
  }

  return { seed, rarity, species, eye, hat, shiny, stats };
}

function rollSoul(rng) {
  return {
    name: NAME_POOL[Math.floor(rng() * NAME_POOL.length)],
    personality: PERSONALITY_POOL[Math.floor(rng() * PERSONALITY_POOL.length)],
  };
}

function loadStored() {
  const p = buddyPath();
  if (!fs.existsSync(p)) return null;
  try {
    return JSON.parse(fs.readFileSync(p, 'utf8'));
  } catch {
    return null;
  }
}

function saveStored(soul) {
  const home = buddyHome();
  if (!fs.existsSync(home)) fs.mkdirSync(home, { recursive: true });
  fs.writeFileSync(buddyPath(), `${JSON.stringify(soul, null, 2)}\n`, 'utf8');
}

function getCompanion() {
  const bones = rollBones();
  const stored = loadStored();
  if (stored && stored.name) {
    return { ...bones, name: stored.name, personality: stored.personality, hatchedAt: stored.hatchedAt };
  }
  return { ...bones, name: null, personality: null, hatchedAt: null };
}

function renderSprite(bones, frame = 0) {
  const frames = BODIES[bones.species] || BODIES.blob;
  let idx = frame;
  if (frame < 0) idx = 2; // blink uses last frame convention
  const raw = frames[idx % frames.length];
  const lines = raw.map((line) => line.replace(/\{E\}/g, bones.eye));
  if (bones.hat !== 'none' && !lines[0].trim()) {
    lines[0] = HAT_LINES[bones.hat] || HAT_LINES.none;
  }
  if (!lines[0].trim() && frames.every((f) => !f[0].trim())) {
    lines.shift();
  }
  return lines;
}

function renderFace(bones) {
  const e = bones.eye;
  const map = {
    duck: `(${e}>`,
    fox: `(${e}${e})`,
    blob: `(${e}${e})`,
    cat: `=${e}ω${e}=`,
    dragon: `<${e}~${e}>`,
    owl: `((${e})(${e}))`,
    penguin: `(${e}>)`,
    turtle: `(${e}${e})`,
    ghost: `/${e}${e}\\`,
    rabbit: `(${e}..${e})`,
    robot: `[${e}${e}]`,
    mushroom: `|${e} ${e}|`,
    chip: `|${e}${e}|`,
    crane: `(${e}>`,
    panda: `(${e}${e})`,
    axolotl: `~(${e}${e})~`,
    cloud: `((${e}${e}))`,
    tensor: `|${e}${e}|`,
  };
  return map[bones.species] || `(${e}${e})`;
}

function colorSprite(lines, bones) {
  const paint = bones.shiny ? c.accent : RARITY_COLOR[bones.rarity] || c.brand;
  return lines.map((l) => paint(l));
}

function bubbleLine(text) {
  return c.mute('╭─ ') + c.ink(text) + c.mute(' ─╮');
}

function bar(n, width = 10) {
  const filled = Math.round((n / 100) * width);
  return c.brand('█'.repeat(filled)) + c.mute('░'.repeat(width - filled));
}

function clearLines(n) {
  for (let i = 0; i < n; i += 1) process.stdout.write('\x1b[1A\x1b[2K');
}

function writeBlock(lines) {
  process.stdout.write(`${lines.join('\n')}\n`);
}

function companionCard(buddy, { bubble = null } = {}) {
  const sprite = colorSprite(renderSprite(buddy, 0), buddy);
  const stars = RARITY_STARS[buddy.rarity];
  const shiny = buddy.shiny ? c.accent(' ✦ SHINY') : '';
  const face = renderFace(buddy);
  const title = `${c.accent(buddy.name || '???')}  ${face}  ${RARITY_COLOR[buddy.rarity](stars)}${shiny}`;
  const meta = `${c.mute(buddy.species)} · ${c.mute(buddy.rarity)}${buddy.hat !== 'none' ? c.mute(` · hat:${buddy.hat}`) : ''}`;
  const stats = STAT_NAMES.map((s) => `  ${c.mute(s.padEnd(10))} ${bar(buddy.stats[s])} ${c.mute(String(buddy.stats[s]))}`).join('\n');
  const left = sprite.join('\n');
  const personality = buddy.personality ? c.mute(`“${buddy.personality}”`) : c.mute('（尚未破壳）');
  const bub = bubble ? `\n${bubbleLine(bubble)}` : '';
  return boxen(`${title}\n${meta}\n\n${left}\n\n${personality}\n${stats}${bub}`, {
    padding: 1,
    margin: { top: 0, bottom: 1, left: 1, right: 1 },
    borderStyle: 'round',
    borderColor: buddy.shiny ? 'magenta' : 'cyan',
    dimBorder: !buddy.shiny,
  });
}

async function animateIdle(buddy, { ticks = 8, delay = 480, bubble = null } = {}) {
  const heightRef = { n: 0 };
  for (let t = 0; t < ticks; t += 1) {
    const frame = IDLE_CYCLE[t % IDLE_CYCLE.length];
    const lines = colorSprite(renderSprite(buddy, frame), buddy);
    const face = renderFace(buddy);
    const name = buddy.name || 'buddy';
    const bub = bubble && t < 4 ? `  ${bubbleLine(bubble)}` : '';
    const block = [
      `  ${c.accent(name)} ${c.mute(face)} ${RARITY_COLOR[buddy.rarity](RARITY_STARS[buddy.rarity])}`,
      ...lines.map((l) => `  ${l}`),
      bub || '  ',
    ];
    if (t > 0) clearLines(heightRef.n);
    writeBlock(block);
    heightRef.n = block.length;
    // eslint-disable-next-line no-await-in-loop
    await sleep(delay);
  }
  return heightRef.n;
}

async function floatingHearts(buddy) {
  const base = colorSprite(renderSprite(buddy, 1), buddy);
  const hearts = ['  ♥', ' ♥ ♥', '♥  ♥ ♥', '  ♥♥', ' ♥'];
  for (const h of hearts) {
    clearLines(base.length + 2);
    writeBlock([
      `  ${c.accent(buddy.name)} ${c.mute(renderFace(buddy))}`,
      ...base.map((l) => `  ${l}`),
      `  ${c.accent(h)}`,
    ]);
    // eslint-disable-next-line no-await-in-loop
    await sleep(160);
  }
}

async function hatchAnimation() {
  const eggs = [
    ['    _____   ', '   /     \\  ', '  |  . .  | ', '  |       | ', '   \\_____/  '],
    ['    _____   ', '   /  ~  \\  ', '  |  . .  | ', '  |   *   | ', '   \\_____/  '],
    ['    __  __  ', '   /  \\/  \\ ', '  |  . .  | ', '  |  ***  | ', '   \\_  _/  '],
    ['   \\  **  / ', '    \\ ** /  ', '     \\**/   ', '      **/   ', '     *  *   '],
  ];
  for (const frame of eggs) {
    writeBlock(frame.map((l) => c.mute(l)));
    // eslint-disable-next-line no-await-in-loop
    await sleep(220);
    clearLines(frame.length);
  }
}

function ensureHatched() {
  let buddy = getCompanion();
  if (buddy.name) return { buddy, fresh: false };
  const rng = mulberry32(fnv1a(`${buddy.seed}|soul`));
  const soul = rollSoul(rng);
  const stored = { ...soul, hatchedAt: Date.now() };
  saveStored(stored);
  buddy = { ...buddy, ...stored };
  return { buddy, fresh: true };
}

async function showBuddyScene({ firstRun = false } = {}) {
  const { buddy, fresh } = ensureHatched();

  if (fresh || firstRun) {
    console.log(c.mute('\n  一颗蛋在暖着……\n'));
    await hatchAnimation();
    console.log(c.ok(`  ✦ ${buddy.name} 破壳了！`) + c.mute(`  ${buddy.species} · ${buddy.rarity}\n`));
    await sleep(200);
  }

  const greet = BUBBLES.greet[Math.floor(Math.random() * BUBBLES.greet.length)];
  console.log(companionCard(buddy, { bubble: fresh ? BUBBLES.hatch[0] : greet }));
  await animateIdle(buddy, {
    ticks: firstRun || fresh ? 10 : 6,
    delay: 420,
    bubble: fresh ? BUBBLES.hatch[1] : greet,
  });
  console.log('');
  return buddy;
}

async function interactBuddy(buddy) {
  if (!process.stdin.isTTY || !inquirer) {
    await floatingHearts(buddy);
    console.log(c.mute(`  ${buddy.name} 蹭了蹭你（非交互模式）\n`));
    return 'go';
  }

  const { action } = await inquirer.prompt([
    {
      type: 'list',
      name: 'action',
      message: c.brand(`${buddy.name} 想做什么？`),
      choices: [
        { name: `摸摸 ${buddy.name}  ♥`, value: 'pet' },
        { name: '喂一颗算子饼干 🍪', value: 'feed' },
        { name: '再看一眼卡片', value: 'card' },
        { name: '出发 →', value: 'go' },
      ],
    },
  ]);

  if (action === 'pet') {
    await floatingHearts(buddy);
    const line = BUBBLES.pet[Math.floor(Math.random() * BUBBLES.pet.length)];
    console.log(`  ${bubbleLine(line)}\n`);
  } else if (action === 'feed') {
    await animateIdle(buddy, { ticks: 4, delay: 300, bubble: BUBBLES.feed[0] });
    console.log(c.ok(`  ${buddy.name} 吃完了，CHAOS 好像又高了一点\n`));
  } else if (action === 'card') {
    console.log(companionCard(buddy));
  } else {
    await animateIdle(buddy, { ticks: 3, delay: 280, bubble: BUBBLES.idle[2] });
  }
  return action;
}

/** Splash entry — CC-like buddy moment. */
async function interactPet({ force = false } = {}) {
  const buddy = await showBuddyScene({ firstRun: force });
  await interactBuddy(buddy);
  return buddy;
}

async function walkAcross() {
  // Keep API: short side-scuttle using face only (CC keeps sprite docked).
  const { buddy } = ensureHatched();
  const face = renderFace(buddy);
  for (let x = 0; x <= 24; x += 2) {
    process.stdout.write(`\r${' '.repeat(x)}${c.accent(face)} ${c.mute(buddy.name || '')}   `);
    // eslint-disable-next-line no-await-in-loop
    await sleep(45);
  }
  process.stdout.write('\n');
}

async function react(kind = 'hop') {
  const { buddy } = ensureHatched();
  if (kind === 'eat') {
    await animateIdle(buddy, { ticks: 4, delay: 260, bubble: BUBBLES.feed[0] });
  } else if (kind === 'wave') {
    await animateIdle(buddy, { ticks: 5, delay: 300, bubble: BUBBLES.greet[0] });
  } else {
    await floatingHearts(buddy);
  }
}

async function buddyCommand() {
  const buddy = await showBuddyScene({ firstRun: false });
  await interactBuddy(buddy);
  console.log(c.mute(`  存档: ${buddyPath()}`));
  console.log(c.mute('  换种子: set REVIEWAGENT_BUDDY_SEED=anything\n'));
}

module.exports = {
  SPECIES,
  getCompanion,
  ensureHatched,
  renderSprite,
  renderFace,
  companionCard,
  showBuddyScene,
  interactBuddy,
  interactPet,
  walkAcross,
  animateIdle: animateIdle,
  react,
  floatingHearts,
  buddyCommand,
  buddyPath,
};
