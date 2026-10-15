#!/usr/bin/env node
/**
 * ReviewAgent — Hermes / Claude Code–style global CLI
 */

const { spawn } = require('child_process');
const path = require('path');
const { findPython } = require('./python-launcher');
const {
  splash,
  spinner,
  sleep,
  readConfig,
  hasUsableApiKey,
  c,
} = require('./ui');
const { runOnboarding } = require('./onboard');
const { buddyCommand } = require('./buddy');

const PROJECT_ROOT = path.join(__dirname, '..');
const PYTHON_SCRIPT = path.join(PROJECT_ROOT, 'review.py');

function runPython(args) {
  try {
    const python = findPython();
    const child = spawn(python.command, [...python.args, PYTHON_SCRIPT, ...args], {
      stdio: 'inherit',
      cwd: process.cwd(),
      env: {
        ...process.env,
        REVIEWAGENT_NODE_UI: '1',
        FORCE_COLOR: process.env.FORCE_COLOR || '1',
        TERM: process.env.TERM || 'xterm-256color',
        // Windows: Enter=send, Shift+Enter=newline, Ctrl+C exits.
        // Set REVIEWAGENT_SMART_INPUT=0 to force plain input()+/paste.
        REVIEWAGENT_SMART_INPUT: process.env.REVIEWAGENT_SMART_INPUT || '1',
      },
      windowsHide: false,
    });

    const killChild = () => {
      try {
        if (!child.killed) {
          child.kill('SIGTERM');
        }
      } catch (_) {
        /* ignore */
      }
      try {
        if (process.platform === 'win32' && child.pid) {
          spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], {
            stdio: 'ignore',
            windowsHide: true,
          });
        }
      } catch (_) {
        /* ignore */
      }
    };

    const onSigInt = () => {
      killChild();
      process.exit(130);
    };
    process.on('SIGINT', onSigInt);
    process.on('SIGTERM', onSigInt);

    child.on('close', (code) => {
      process.removeListener('SIGINT', onSigInt);
      process.removeListener('SIGTERM', onSigInt);
      process.exit(code == null ? 1 : code);
    });
    child.on('error', (err) => {
      console.error(c.warn('启动失败:'), err.message);
      process.exit(1);
    });
  } catch (err) {
    console.error('\n[ERROR]', err.message);
    console.error('\n请安装 Python 3.7+: https://www.python.org/downloads/');
    process.exit(1);
  }
}

function isWake(args) {
  return args.length === 0 || args[0] === 'chat';
}

function isConfigWizard(args) {
  return args[0] === 'config' && (args.includes('--wizard') || args.includes('-w'));
}

function wantsHelp(args) {
  return args.includes('--help') || args.includes('-h') || args.includes('--version');
}

async function bootAndWake(pyArgs) {
  const spin = spinner('唤醒 Ascend AI Infra Agent…');
  spin.start();
  await sleep(480);
  spin.succeed(c.ok('Agent 已就绪'));
  await sleep(120);
  runPython(pyArgs);
}

async function main() {
  const args = process.argv.slice(2);

  if (wantsHelp(args) && !isConfigWizard(args)) {
    runPython(args);
    return;
  }

  if (args[0] === 'buddy' || args[0] === 'pet') {
    await buddyCommand();
    return;
  }

  if (isConfigWizard(args)) {
    await splash({ firstRun: true });
    const ok = await runOnboarding();
    process.exit(ok ? 0 : 1);
  }

  if (isWake(args) && !hasUsableApiKey(readConfig())) {
    await splash({ firstRun: true });
    const ok = await runOnboarding();
    if (!ok) process.exit(1);
    await splash({ firstRun: false });
    const pyArgs = args.length === 0 ? ['chat'] : args;
    await bootAndWake(pyArgs);
    return;
  }

  if (isWake(args)) {
    await splash({ firstRun: false });
    const pyArgs = args.length === 0 ? ['chat'] : args;
    await bootAndWake(pyArgs);
    return;
  }

  runPython(args);
}

main().catch((err) => {
  console.error('[ERROR]', err && err.message ? err.message : err);
  process.exit(1);
});
