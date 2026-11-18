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
  if (result.status !== 0) {
    process.exitCode = result.status === null ? 1 : result.status;
  } else {
    const wizard = spawnSync(process.execPath, [path.join(__dirname, '..', 'tests', 'test_wizard_confirm.js')], {
      cwd: path.join(__dirname, '..'), stdio: 'inherit', windowsHide: true,
    });
    if (wizard.error) throw wizard.error;
    process.exitCode = wizard.status === null ? 1 : wizard.status;
  }
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
