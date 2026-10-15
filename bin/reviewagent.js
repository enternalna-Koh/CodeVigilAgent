#!/usr/bin/env node
/**
 * ReviewAgent — Hermes-style global CLI
 *
 *   npm install -g reviewagent
 *   reviewagent                 # wake AI Infra agent (chat)
 *   reviewagent review          # git workspace review
 *   reviewagent config          # provider / model setup
 *   reviewagent doctor          # environment check
 *
 * Compatible with cc-switch env injection:
 *   OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL
 *   ANTHROPIC_API_KEY / AI_PROVIDER / AI_API_KEY / AI_MODEL
 */

const { spawn } = require('child_process');
const path = require('path');
const { findPython } = require('./python-launcher');

const PROJECT_ROOT = path.join(__dirname, '..');
const PYTHON_SCRIPT = path.join(PROJECT_ROOT, 'review.py');

function runPython(args) {
  try {
    const python = findPython();
    const child = spawn(python.command, [...python.args, PYTHON_SCRIPT, ...args], {
      stdio: 'inherit',
      cwd: process.cwd(),
      env: process.env,
    });
    child.on('close', (code) => process.exit(code == null ? 1 : code));
    child.on('error', (err) => {
      console.error('启动失败:', err.message);
      process.exit(1);
    });
  } catch (err) {
    console.error('\n[ERROR]', err.message);
    console.error('\n请安装 Python 3.7+: https://www.python.org/downloads/');
    process.exit(1);
  }
}

runPython(process.argv.slice(2));
