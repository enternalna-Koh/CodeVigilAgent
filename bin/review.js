#!/usr/bin/env node
/**
 * ReviewAgent CLI Entry
 * 全局命令: review
 */

const { spawn } = require('child_process');
const path = require('path');
const { findPython } = require('./python-launcher');

// 项目根目录
const PROJECT_ROOT = path.join(__dirname, '..');

// Python 脚本路径
const PYTHON_SCRIPT = path.join(PROJECT_ROOT, 'review.py');

// Logo
const LOGO = `
    ____            _                ___                    __
   / __ \\___ _   __(_)__ _      __  /   | ____ ____  ____  / /_
  / /_/ / _ \\ | / / / _ \\ | /| / / / /| |/ __ \`/ _ \\/ __ \\/ __/
 / _, _/  __/ |/ / /  __/ |/ |/ / / ___ / /_/ /  __/ / / / /_
/_/ |_|\\___/|___/_/\\___/|__/|__/ /_/  |_\\__, /\\___/_/ /_/\\__/
                                        /____/
`;

// 显示欢迎信息
function showWelcome() {
  console.log(LOGO);
  console.log('智能代码审查助手 - 专为昇腾 NPU 打造');
  console.log('='.repeat(70));
  console.log();
}

// 运行 Python 脚本
async function runPython(args) {
  try {
    const python_ = findPython();

    // 显示 Logo
    // JSON and command output must stay machine readable. The Python CLI
    // owns the interactive UI so launchers do not print a second banner.

    // 启动 Python 脚本（python_.args 保留 `py -3` 这类启动器参数）
    const python = spawn(python_.command, [...python_.args, PYTHON_SCRIPT, ...args], {
      stdio: 'inherit',
      cwd: process.cwd()
    });

    python.on('close', (code) => {
      process.exit(code);
    });

    python.on('error', (err) => {
      console.error('启动失败:', err.message);
      process.exit(1);
    });

  } catch (err) {
    console.error('\n[ERROR]', err.message);
    console.error('\n请安装 Python 3.7+: https://www.python.org/downloads/');
    console.error('\n或使用以下命令检查:');
    console.error('  python --version');
    process.exit(1);
  }
}

// 主函数
function main() {
  const args = process.argv.slice(2);
  runPython(args);
}

// 执行
main();
