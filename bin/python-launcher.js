/**
 * 选择可用的 Python 解释器，供 bin/review.js 与 install.js 共用。
 *
 * Windows 上 PATH 里的 `python` 可能只是应用执行别名（没有安装真实解释器时
 * 退出码非 0），而 `py -3` 启动器可用，所以按顺序逐个验证。
 */

const { spawnSync } = require('child_process');

const WINDOWS_CANDIDATES = [
  { command: 'python', args: [] },
  { command: 'py', args: ['-3'] },
];
const POSIX_CANDIDATES = [
  { command: 'python3', args: [] },
  { command: 'python', args: [] },
];

function candidates(platform) {
  return platform === 'win32' ? WINDOWS_CANDIDATES : POSIX_CANDIDATES;
}

// 只有退出码为 0 且输出 "Python x.y.z" 才算可用，避免把应用别名桩程序当成解释器。
function probe(candidate) {
  const result = spawnSync(candidate.command, [...candidate.args, '--version'], {
    encoding: 'utf-8',
    windowsHide: true,
  });
  if (result.error || result.status !== 0) return null;
  const match = /Python\s+\d+\.\d+[^\s]*/i.exec(`${result.stdout}${result.stderr}`);
  return match ? match[0] : null;
}

/**
 * @returns {{command: string, args: string[], version: string}} args 是解释器自带的启动参数（如 py 的 -3）
 * @throws 没有可用解释器时抛出 Error
 */
function findPython(platform = process.platform, probeFn = probe) {
  for (const candidate of candidates(platform)) {
    const version = probeFn(candidate);
    if (version) return { ...candidate, version };
  }
  const tried = candidates(platform)
    .map((c) => [c.command, ...c.args].join(' '))
    .join('、');
  throw new Error(`Python 未安装或不在 PATH 中（已尝试: ${tried}）`);
}

module.exports = { findPython, probe };
