# 发布到 npm

将 ReviewAgent 发布为全局可用的 npm 包

---

## 📋 准备工作

### 1. 注册 npm 账号

访问 https://www.npmjs.com/signup 注册账号

### 2. 登录 npm

```bash
npm login
```

输入用户名、密码、邮箱

---

## 📦 发布步骤

### 1. 安装 Node.js 依赖

```bash
cd D:\Agent-ReviewAgent
npm install
```

这会安装：
- chalk - 终端颜色
- inquirer - 交互式提示
- ora - 进度指示器
- boxen - 边框

### 2. 测试本地安装

```bash
npm link
```

然后测试：

```bash
review
```

### 3. 发布到 npm

```bash
# 首次发布
npm publish --access public

# 后续更新
npm version patch  # 1.0.0 -> 1.0.1
npm publish
```

---

## 🚀 用户安装

发布后，任何人都可以：

```bash
npm install -g @reviewagent/cli
```

然后全局使用：

```bash
review
```

---

## 🔄 更新版本

```bash
# 修复版本 (1.0.0 -> 1.0.1)
npm version patch

# 小版本 (1.0.0 -> 1.1.0)
npm version minor

# 大版本 (1.0.0 -> 2.0.0)
npm version major

# 发布
npm publish
```

---

## 📊 包信息

- **包名**: `@reviewagent/cli`
- **命令**: `review`
- **版本**: `1.0.0`
- **依赖**: Node.js >= 14, Python >= 3.7

---

## 🎯 现在本地测试

不发布也可以测试完整功能：

```bash
# 1. 安装依赖
npm install

# 2. 链接到全局
npm link

# 3. 测试命令
review

# 4. 取消链接
npm unlink -g @reviewagent/cli
```

---

## 💡 包结构

```
@reviewagent/cli
├── package.json        npm 配置
├── install.js          安装脚本
├── bin/
│   └── review.js       CLI 入口
├── review.py           Python 主程序
├── scripts/            Python 模块
└── config/             配置文件
```

---

## 🌟 与 Claude Code 对比

| 特性 | Claude Code | ReviewAgent |
|------|-------------|-------------|
| 安装 | `npm install -g @anthropic-ai/claude-code` | `npm install -g @reviewagent/cli` |
| 命令 | `claude` | `review` |
| 语言 | JavaScript/TypeScript | Node.js + Python |
| 专业领域 | 通用 AI | 昇腾 NPU |

---

## 🎊 完成！

现在 ReviewAgent 可以像 Claude Code 一样：

```bash
npm install -g @reviewagent/cli
review
```

**一键安装，全局可用！** 🚀
