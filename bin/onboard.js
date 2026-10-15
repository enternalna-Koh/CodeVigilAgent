/**
 * First-run API setup wizard (Claude Code–style guided onboarding).
 */
const fs = require('fs');
const { homeDir, configPath, readConfig, c, boxen, spinner, sleep } = require('./ui');
const { react } = require('./buddy');

let inquirer;
try {
  inquirer = require('inquirer');
} catch {
  inquirer = null;
}

/** OpenAI-compatible catalogs (saved as provider=openai + base_url). */
const PROVIDERS = [
  {
    name: 'DeepSeek',
    value: 'deepseek',
    hint: 'platform.deepseek.com',
    models: [
      'deepseek-chat',
      'deepseek-reasoner',
      'deepseek-coder',
      'deepseek-v3',
      'deepseek-v3.1',
      'deepseek-v3.2',
      'deepseek-r1',
      'deepseek-r1-0528',
      'deepseek-r1-distill-qwen-32b',
      'deepseek-r1-distill-llama-70b',
    ],
  },
  {
    name: 'OpenAI / 兼容网关（中转、本地、vLLM）',
    value: 'openai',
    hint: '可自定义 base_url',
    openaiCompat: true,
    models: [
      'gpt-4o',
      'gpt-4o-mini',
      'gpt-4.1',
      'gpt-4.1-mini',
      'gpt-4.1-nano',
      'gpt-4-turbo',
      'gpt-4',
      'o1',
      'o1-mini',
      'o1-pro',
      'o3',
      'o3-mini',
      'o4-mini',
      'gpt-3.5-turbo',
    ],
  },
  {
    name: 'Claude (Anthropic)',
    value: 'claude',
    hint: 'console.anthropic.com',
    models: [
      'claude-opus-4-20250514',
      'claude-sonnet-4-20250514',
      'claude-3-7-sonnet-20250219',
      'claude-3-5-sonnet-20241022',
      'claude-3-5-haiku-20241022',
      'claude-3-opus-20240229',
      'claude-3-sonnet-20240229',
      'claude-3-haiku-20240307',
    ],
  },
  {
    name: 'Google Gemini',
    value: 'gemini',
    hint: 'aistudio.google.com · OpenAI 兼容',
    openaiCompat: true,
    defaultBase: 'https://generativelanguage.googleapis.com/v1beta/openai/',
    models: [
      'gemini-2.5-pro',
      'gemini-2.5-flash',
      'gemini-2.5-flash-lite',
      'gemini-2.0-flash',
      'gemini-2.0-flash-lite',
      'gemini-1.5-pro',
      'gemini-1.5-flash',
      'gemini-1.5-flash-8b',
      'gemini-exp-1206',
    ],
  },
  {
    name: 'xAI Grok（马斯克）',
    value: 'xai',
    hint: 'console.x.ai',
    openaiCompat: true,
    defaultBase: 'https://api.x.ai/v1',
    models: [
      'grok-4',
      'grok-4-latest',
      'grok-3',
      'grok-3-mini',
      'grok-3-fast',
      'grok-3-mini-fast',
      'grok-2',
      'grok-2-latest',
      'grok-2-vision-1212',
      'grok-beta',
    ],
  },
  {
    name: 'MiniMax',
    value: 'minimax',
    hint: 'platform.minimaxi.com · 对话请选 Text/M1，勿选 VL',
    openaiCompat: true,
    defaultBase: 'https://api.minimax.chat/v1',
    models: [
      'MiniMax-M1',
      'MiniMax-Text-01',
      'abab6.5s-chat',
      'abab6.5-chat',
      'abab6.5g-chat',
      'abab6.5t-chat',
      'abab5.5s-chat',
      'abab5.5-chat',
    ],
  },
  {
    name: '通义千问 Qwen（阿里）',
    value: 'qwen',
    hint: 'dashscope.aliyun.com',
    openaiCompat: true,
    defaultBase: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    models: [
      'qwen-max',
      'qwen-max-latest',
      'qwen-plus',
      'qwen-plus-latest',
      'qwen-turbo',
      'qwen-turbo-latest',
      'qwen-long',
      'qwen-coder-plus',
      'qwen-coder-turbo',
      'qwen2.5-72b-instruct',
      'qwen2.5-32b-instruct',
      'qwen2.5-14b-instruct',
      'qwen2.5-7b-instruct',
      'qwen2.5-coder-32b-instruct',
      'qwq-32b',
      'qwq-plus',
      'qwen3-235b-a22b',
      'qwen3-32b',
      'qwen3-14b',
      'qwen3-8b',
      'qwen-vl-max',
      'qwen-vl-plus',
    ],
  },
  {
    name: '豆包 Doubao（字节跳动）',
    value: 'doubao',
    hint: 'volcengine.com 火山方舟',
    openaiCompat: true,
    defaultBase: 'https://ark.cn-beijing.volces.com/api/v3',
    models: [
      'doubao-seed-1.6',
      'doubao-seed-1.6-flash',
      'doubao-seed-1.6-thinking',
      'doubao-1.5-pro-32k',
      'doubao-1.5-lite-32k',
      'doubao-1.5-thinking-pro',
      'doubao-pro-32k',
      'doubao-pro-128k',
      'doubao-lite-32k',
      'doubao-lite-128k',
      'doubao-vision-pro-32k',
    ],
  },
  {
    name: '混元 Hunyuan（腾讯）',
    value: 'hunyuan',
    hint: 'cloud.tencent.com/hunyuan',
    openaiCompat: true,
    defaultBase: 'https://api.hunyuan.cloud.tencent.com/v1',
    models: [
      'hunyuan-lite',
      'hunyuan-standard',
      'hunyuan-standard-256K',
      'hunyuan-pro',
      'hunyuan-turbo',
      'hunyuan-turbo-latest',
      'hunyuan-large',
      'hunyuan-large-longcontext',
      'hunyuan-role',
      'hunyuan-functioncall',
      'hunyuan-code',
      'hunyuan-vision',
    ],
  },
  {
    name: '智谱 GLM',
    value: 'glm',
    hint: 'open.bigmodel.cn',
    models: [
      'glm-4',
      'glm-4-plus',
      'glm-4-air',
      'glm-4-airx',
      'glm-4-flash',
      'glm-4-flashx',
      'glm-4-long',
      'glm-4-0520',
      'glm-4v',
      'glm-4v-plus',
      'glm-z1-air',
      'glm-z1-airx',
      'glm-z1-flash',
      'glm-3-turbo',
    ],
  },
  {
    name: 'Kimi (Moonshot)',
    value: 'kimi',
    hint: 'platform.moonshot.cn',
    openaiCompat: true,
    defaultBase: 'https://api.moonshot.cn/v1',
    models: [
      'moonshot-v1-8k',
      'moonshot-v1-32k',
      'moonshot-v1-128k',
      'kimi-latest',
      'kimi-thinking-preview',
      'kimi-k2-0711-preview',
    ],
  },
  {
    name: '硅基流动 SiliconFlow',
    value: 'siliconflow',
    hint: 'cloud.siliconflow.cn · 多模型/开源聚合',
    openaiCompat: true,
    defaultBase: 'https://api.siliconflow.cn/v1',
    models: [
      'deepseek-ai/DeepSeek-V3',
      'deepseek-ai/DeepSeek-R1',
      'MiniMaxAI/MiniMax-M1-80k',
      'Qwen/Qwen2.5-72B-Instruct',
      'Qwen/QwQ-32B',
      'Qwen/Qwen3-235B-A22B',
      'THUDM/GLM-4-9B-0414',
      'google/gemma-3-27b-it',
      'meta-llama/Llama-3.3-70B-Instruct',
      'Pro/deepseek-ai/DeepSeek-V3',
      'Pro/deepseek-ai/DeepSeek-R1',
    ],
  },
];

function ensureHome() {
  const home = homeDir();
  if (!fs.existsSync(home)) fs.mkdirSync(home, { recursive: true });
  return home;
}

function writeConfig(data) {
  ensureHome();
  const target = configPath();
  const prev = readConfig() || {};
  const next = { ...prev, ...data };
  fs.writeFileSync(target, `${JSON.stringify(next, null, 2)}\n`, 'utf8');
  return target;
}

/** Native adapters vs OpenAI-compatible HTTP (need base_url). */
const NATIVE = new Set(['deepseek', 'openai', 'claude', 'glm']);

function normalizeProvider(provider, meta) {
  if (meta && meta.openaiCompat && provider !== 'openai') {
    return { fileProvider: 'openai', logical: provider };
  }
  if (!NATIVE.has(provider)) {
    return { fileProvider: 'openai', logical: provider };
  }
  return { fileProvider: provider, logical: provider };
}

async function runOnboarding() {
  console.log(
    boxen(
      `${c.accent('✦ 欢迎使用 ReviewAgent')}\n\n` +
        `${c.mute('像 Claude Code 一样，先完成 API 配置。')}\n` +
        `${c.mute('密钥只保存在本机')} ${c.brand(configPath())}\n` +
        `${c.accent('buddy')} ${c.mute('会像 Claude Code 一样坐在旁边～')}`,
      {
        padding: 1,
        margin: 1,
        borderStyle: 'round',
        borderColor: 'magenta',
        title: '首次配置',
        titleAlignment: 'center',
      },
    ),
  );

  if (!inquirer) {
    console.log(c.warn('缺少 inquirer，请运行: npm install'));
    console.log(c.mute('或手动编辑'), configPath());
    return false;
  }

  const { provider } = await inquirer.prompt([
    {
      type: 'list',
      name: 'provider',
      message: c.brand('选择模型提供商'),
      pageSize: 16,
      choices: PROVIDERS.map((p) => ({
        name: `${p.name}  ${c.mute(p.hint)}`,
        value: p.value,
      })),
    },
  ]);

  const meta = PROVIDERS.find((p) => p.value === provider);
  const { modelPick } = await inquirer.prompt([
    {
      type: 'list',
      name: 'modelPick',
      message: c.brand('选择模型（可翻页）'),
      pageSize: 16,
      choices: [
        ...meta.models.map((m) => ({ name: m, value: m })),
        new inquirer.Separator(),
        { name: c.mute('自定义输入…'), value: '__custom__' },
      ],
    },
  ]);

  let model = modelPick;
  if (modelPick === '__custom__') {
    const ans = await inquirer.prompt([
      {
        type: 'input',
        name: 'model',
        message: '自定义模型 ID（豆包等可填接入点 ep-xxx）',
        validate: (v) => (!!String(v).trim() ? true : '不能为空'),
      },
    ]);
    model = ans.model.trim();
  }

  const needsBase = !!(meta.openaiCompat || meta.defaultBase);
  let base_url = meta.defaultBase || '';
  if (needsBase) {
    const ans = await inquirer.prompt([
      {
        type: 'input',
        name: 'base_url',
        message: 'OpenAI 兼容 base_url',
        default: meta.defaultBase || 'https://api.openai.com/v1',
      },
    ]);
    base_url = ans.base_url.trim();
  }

  const { api_key } = await inquirer.prompt([
    {
      type: 'password',
      name: 'api_key',
      message: 'API Key（输入时隐藏）',
      mask: '✦',
      validate: (v) => {
        const s = String(v || '').trim();
        if (!s || s === 'YOUR_API_KEY_HERE') return '请填写真实 API Key';
        if (s.length < 8) return 'Key 太短，请检查';
        return true;
      },
    },
  ]);

  const spin = spinner('buddy 正在把配置藏进本机…');
  spin.start();
  await sleep(420);
  const { fileProvider } = normalizeProvider(provider, meta);
  const saved = writeConfig({
    provider: fileProvider,
    model,
    api_key: api_key.trim(),
    base_url: base_url || '',
    label: provider,
  });
  spin.succeed(c.ok(`配置已保存 → ${saved}`));
  await react('hop');

  console.log(
    boxen(
      `${c.ok('✓ 配置完成')}  ${c.accent('buddy ★')}\n\n` +
        `${c.mute('provider')}  ${provider} → ${fileProvider}\n` +
        `${c.mute('model')}     ${model}\n` +
        (base_url ? `${c.mute('base_url')}  ${base_url}\n` : '') +
        `\n${c.accent('正在启动 Agent…')}`,
      {
        padding: 1,
        margin: { top: 1, bottom: 1, left: 1, right: 1 },
        borderStyle: 'round',
        borderColor: 'green',
      },
    ),
  );
  await sleep(280);
  return true;
}

module.exports = { runOnboarding, writeConfig, PROVIDERS };
