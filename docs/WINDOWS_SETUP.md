# 将 ReviewAgent 添加到 Windows PATH 的详细步骤

---

## 方法 1: 图形界面（推荐新手）

1. **复制路径**
   ```
   D:\Agent-ReviewAgent\bin
   ```

2. **打开系统属性**
   - 按 `Win + R`，输入 `sysdm.cpl`，回车
   - 或：右键 "此电脑" → 属性 → 高级系统设置

3. **编辑环境变量**
   - 点击 "环境变量" 按钮
   - 在 "系统变量" 区域找到 `Path`
   - 点击 "编辑"

4. **添加路径**
   - 点击 "新建"
   - 粘贴: `D:\Agent-ReviewAgent\bin`
   - 点击 "确定"

5. **应用更改**
   - 一路点击 "确定" 关闭所有窗口

6. **测试**
   - 重启 PowerShell 或 CMD
   - 输入: `review`

---

## 方法 2: PowerShell 命令（推荐高级用户）

以管理员身份打开 PowerShell：

```powershell
# 添加到系统 PATH
$newPath = "D:\Agent-ReviewAgent\bin"
$currentPath = [Environment]::GetEnvironmentVariable("Path", "Machine")
[Environment]::SetEnvironmentVariable("Path", "$currentPath;$newPath", "Machine")

# 刷新当前会话
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine")

# 测试
review --version
```

---

## 方法 3: 临时别名（本次会话）

在当前 PowerShell 中：

```powershell
Set-Alias review "D:\Agent-ReviewAgent\bin\review.bat"

# 测试
review
```

要永久保存，添加到 PowerShell 配置文件：

```powershell
# 编辑配置文件
notepad $PROFILE

# 添加这行
Set-Alias review "D:\Agent-ReviewAgent\bin\review.bat"
```

---

## 验证安装

```powershell
# 检查 PATH
echo $env:Path

# 测试命令
review --version

# 进入对话模式
review
```

---

## 完成！

现在你可以在任何地方使用 `review` 命令了！ 🎉
