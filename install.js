#!/usr/bin/env node
/**
 * ReviewAgent 安装脚本
 * npm install -g @reviewagent/cli 后自动执行
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const chalk = require('chalk');
const boxen = require('boxen');

console.log('\n');
console.log(boxen(
  chalk.bold.cyan('ReviewAgent') + ' 安装中...',
  {
    padding: 1,
    margin: 1,
    borderStyle: 'round',
    borderColor: 'cyan'
  }
));

// 检查 Python
function checkPython() {
  try {
    const pythonCmd = process.platform === 'win32' ? 'python' : 'python3';
    const version = execSync(`${pythonCmd} --version`, { encoding: 'utf-8' });
    console.log(chalk.green('✓'), 'Python 已安装:', version.trim());
    return true;
  } catch (err) {
    console.log(chalk.red('✗'), 'Python 未找到');
    return false;
  }
}

// 安装 Python 依赖（如果需要）
function installPythonDeps() {
  const requirementsPath = path.join(__dirname, 'requirements.txt');

  if (fs.existsSync(requirementsPath)) {
    try {
      console.log(chalk.yellow('⋯'), '安装 Python 依赖...');
      execSync('pip install -r requirements.txt', { stdio: 'inherit' });
      console.log(chalk.green('✓'), 'Python 依赖已安装');
    } catch (err) {
      console.log(chalk.yellow('⚠'), 'Python 依赖安装失败（可选）');
    }
  }
}

// 创建配置目录
function createConfigDir() {
  const configDir = path.join(__dirname, 'config');
  if (!fs.existsSync(configDir)) {
    fs.mkdirSync(configDir, { recursive: true });
    console.log(chalk.green('✓'), '配置目录已创建');
  }
}

// 主安装流程
function main() {
  console.log('\n' + chalk.bold('安装步骤:') + '\n');

  // 1. 检查 Python
  const hasPython = checkPython();

  if (!hasPython) {
    console.log('\n' + boxen(
      chalk.yellow.bold('警告\n\n') +
      'ReviewAgent 需要 Python 3.7+ 才能运行\n\n' +
      '请访问: ' + chalk.cyan('https://www.python.org/downloads/') + '\n' +
      '安装 Python 后重新安装 ReviewAgent',
      {
        padding: 1,
        borderStyle: 'round',
        borderColor: 'yellow'
      }
    ));
    process.exit(1);
  }

  // 2. 创建配置目录
  createConfigDir();

  // 3. 安装依赖（可选）
  // installPythonDeps();

  // 完成
  console.log('\n' + boxen(
    chalk.green.bold('✓ 安装完成！\n\n') +
    '现在你可以使用:\n\n' +
    chalk.cyan('  review') + ' - 进入对话模式\n' +
    chalk.cyan('  review code.py') + ' - 快速审查文件\n' +
    chalk.cyan('  review --help') + ' - 查看帮助\n\n' +
    '首次运行会引导你配置 AI 服务',
    {
      padding: 1,
      margin: 1,
      borderStyle: 'round',
      borderColor: 'green'
    }
  ));
}

main();
