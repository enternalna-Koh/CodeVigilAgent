#!/usr/bin/env node
/**
 * postinstall — Hermes-style bootstrap for ReviewAgent
 */

const fs = require('fs');
const path = require('path');
const os = require('os');
const { findPython } = require('./bin/python-launcher');

let chalk, boxen;
try {
  chalk = require('chalk');
  boxen = require('boxen');
} catch {
  chalk = { green: (s) => s, red: (s) => s, yellow: (s) => s, cyan: (s) => s, bold: { cyan: (s) => s, green: (s) => s, yellow: (s) => s } };
  chalk.bold = Object.assign((s) => s, chalk.bold);
  boxen = (s) => s;
}

const HOME = process.env.REVIEWAGENT_HOME || path.join(os.homedir(), '.reviewagent');
const TEMPLATE = path.join(__dirname, 'config', 'ai_config.json.template');
const HOME_CONFIG = path.join(HOME, 'ai_config.json');

function ensureHome() {
  if (!fs.existsSync(HOME)) {
    fs.mkdirSync(HOME, { recursive: true });
    console.log(chalk.green('✓'), `已创建 ${HOME}`);
  }
  if (!fs.existsSync(HOME_CONFIG) && fs.existsSync(TEMPLATE)) {
    fs.copyFileSync(TEMPLATE, HOME_CONFIG);
    console.log(chalk.green('✓'), `已写入配置模板 ${HOME_CONFIG}`);
  }
}

function checkPython() {
  try {
    const found = findPython();
    const launcher = [found.command, ...found.args].join(' ');
    console.log(chalk.green('✓'), `Python: ${found.version}（${launcher}）`);
    return true;
  } catch {
    console.log(chalk.red('✗'), '未找到 Python 3.7+');
    return false;
  }
}

function main() {
  console.log('\n' + boxen(chalk.bold.cyan('ReviewAgent') + ' · Ascend AI Infra', {
    padding: 1, margin: 1, borderStyle: 'round', borderColor: 'cyan',
  }));

  console.log(chalk.bold('安装检查:\n'));
  const ok = checkPython();
  ensureHome();

  if (!ok) {
    console.log('\n' + boxen(
      chalk.yellow.bold('需要 Python\n\n') +
      '请安装 Python 3.7+ 后重试：https://www.python.org/downloads/',
      { padding: 1, borderStyle: 'round', borderColor: 'yellow' },
    ));
  }

  console.log('\n' + boxen(
    chalk.green.bold('唤醒 Agent（类似 hermes）\n\n') +
    chalk.cyan('  reviewagent') + '              # 对话模式\n' +
    chalk.cyan('  reviewagent review') + '       # 审查当前仓库 diff\n' +
    chalk.cyan('  reviewagent search "HCCL"') + ' # 本地案例\n' +
    chalk.cyan('  reviewagent config') + '        # 配置模型\n' +
    chalk.cyan('  reviewagent doctor') + '        # 环境自检\n' +
    chalk.cyan('  ra') + ' / ' + chalk.cyan('review') + '             # 短命令别名\n\n' +
    '模型切换（兼容 cc-switch）:\n' +
    '  导出 OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL\n' +
    '  或 ANTHROPIC_API_KEY，然后直接 ' + chalk.cyan('reviewagent') + '\n' +
    '  文档: docs/CC_SWITCH.md',
    { padding: 1, margin: 1, borderStyle: 'round', borderColor: 'green' },
  ));
}

main();
