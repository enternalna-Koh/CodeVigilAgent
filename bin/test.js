#!/usr/bin/env node
const { spawnSync } = require('child_process');
const path = require('path');
const { findPython } = require('./python-launcher');

try {
  const python = findPython();
  const result = spawnSync(python.command, [...python.args, '-m', 'unittest', 'discover', '-s', 'tests', '-q'], {
    cwd: path.join(__dirname, '..'),
    stdio: 'inherit',
    windowsHide: true,
  });
  if (result.error) throw result.error;
  process.exitCode = result.status === null ? 1 : result.status;
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
