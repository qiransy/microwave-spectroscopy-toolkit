# Microwave Spectroscopy Workflow Skill

面向**气相微波转动光谱（FTMW / CP-FTMW）与配套计算化学**的 AI Agent 领域工作流技能，遵循开放 `SKILL.md` 规范，可与本仓库的 [Pickett Runner](../../pickett-runner/README.md) 配合使用。

## 包含内容

- `SKILL.md`：覆盖文献调研、CREST/Gaussian/ORCA 结果整理、理论与实验参数对照（SPFIT/SPCAT/PGOPHER）、组会进展报告、论文证据缺口审查及图表专业表达的领域规范。
- `references/zotero-profile.md`：微波转动光谱文献库专用 Zotero 标签与笔记字段模板。

## 安装方式

### Codex

将本仓库中的 **整个** `skills/microwave-spectroscopy-workflow/` 文件夹复制到课题目录的 `.agents/skills/`。首次安装时，可在本仓库根目录执行以下命令，把示例路径换成已有的课题目录。如果已存在同名 Skill，先比较内容再决定是否更新。

**Windows（PowerShell）**

```powershell
$project = 'D:\research\my-project'
$dest = Join-Path $project '.agents\skills\microwave-spectroscopy-workflow'
if (Test-Path -LiteralPath $dest) { throw "Skill folder already exists: $dest" }
New-Item -ItemType Directory -Path (Split-Path -Parent $dest) -Force | Out-Null
Copy-Item -LiteralPath 'skills/microwave-spectroscopy-workflow' -Destination $dest -Recurse
```

**macOS / Linux**

```bash
project="/path/to/my-project"
dest="$project/.agents/skills/microwave-spectroscopy-workflow"
mkdir -p "$project/.agents/skills" &&
  mkdir "$dest" &&
  cp -R skills/microwave-spectroscopy-workflow/. "$dest/"
```

确认课题目录下有 `.agents/skills/microwave-spectroscopy-workflow/SKILL.md`，以及同一技能目录里的 `references/zotero-profile.md`。以该课题目录开启 Codex 新对话，从 Skill 选择器选用 `microwave-spectroscopy-workflow`，或在 CLI 中用 `/skills` 检查。 [Codex 官方技能文档](https://learn.chatgpt.com/docs/build-skills)

已在 Windows 测试复制及 Codex 的项目技能识别。实际运行拟合需另外准备 SPFIT/SPCAT 和输入文件。

### Antigravity（整仓直接作为插件安装）
```bash
# macOS / Linux
git clone https://github.com/qiransy/microwave-spectroscopy-toolkit.git ~/.gemini/config/plugins/microwave-spectroscopy-toolkit

# Windows (PowerShell)
git clone https://github.com/qiransy/microwave-spectroscopy-toolkit.git "$env:USERPROFILE\.gemini\config\plugins\microwave-spectroscopy-toolkit"
```

### 其他客户端
仅复制 `skills/microwave-spectroscopy-workflow/` 文件夹到对应项目的技能目录：
- **Cursor / Gemini CLI**：`.agents/skills/microwave-spectroscopy-workflow/`
- **Claude Code**：`.claude/skills/microwave-spectroscopy-workflow/`

> 如需搭配通用论文读写、引用核验、审稿修回与 Origin 绘图技能，可同时安装通用包 [chem-materials-research-kit](https://github.com/qiransy/chem-materials-research-kit)。
