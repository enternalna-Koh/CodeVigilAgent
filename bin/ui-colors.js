/**
 * Shared terminal colors + sleep (no heavy deps cycle).
 */
let chalk;
try {
  chalk = require('chalk');
} catch {
  chalk = new Proxy({}, { get: () => (s) => s });
  chalk.bold = (s) => s;
  chalk.dim = (s) => s;
  chalk.cyan = (s) => s;
  chalk.magenta = (s) => s;
  chalk.green = (s) => s;
  chalk.yellow = (s) => s;
  chalk.white = (s) => s;
  chalk.gray = (s) => s;
  chalk.hex = () => (s) => s;
}

const c = {
  brand: chalk.hex ? chalk.hex('#00C2A8') : chalk.cyan,
  accent: chalk.hex ? chalk.hex('#FF8FAB') : chalk.magenta,
  glow: chalk.hex ? chalk.hex('#7EE8D0') : chalk.cyan,
  ink: chalk.white,
  mute: chalk.gray,
  ok: chalk.green,
  warn: chalk.yellow,
};

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

module.exports = { chalk, c, sleep };
