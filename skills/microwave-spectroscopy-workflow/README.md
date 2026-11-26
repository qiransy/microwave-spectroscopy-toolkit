# Microwave Spectroscopy Workflow Skill

面向**气相微波转动光谱（FTMW / CP-FTMW）与配套计算化学**的 AI Agent 领域工作流技能，遵循开放 `SKILL.md` 规范，可与本仓库的 [Pickett Runner](../../pickett-runner/README.md) 配合使用。

## 包含内容

- `SKILL.md`：覆盖文献调研、CREST/Gaussian/ORCA 结果整理、理论与实验参数对照（SPFIT/SPCAT/PGOPHER）、组会进展报告、论文证据缺口审查及图表专业表达的领域规范。
- `references/zotero-profile.md`：微波转动光谱文献库专用 Zotero 标签与笔记字段模板。

## 安装方式

### Antigravity（整仓直接作为插件安装）
```bash
# macOS / Linux
git clone https://github.com/qiransy/microwave-spectroscopy-toolkit.git ~/.gemini/config/plugins/microwave-spectroscopy-toolkit

# Windows (PowerShell)
git clone https://github.com/qiransy/microwave-spectroscopy-toolkit.git "$env:USERPROFILE\.gemini\config\plugins\microwave-spectroscopy-toolkit"
```

### Codex / Cursor / Claude Code / Gemini CLI
仅复制 `skills/microwave-spectroscopy-workflow/` 文件夹到对应项目的技能目录：
- **Codex / Cursor / Gemini CLI**：`.agents/skills/microwave-spectroscopy-workflow/`
- **Claude Code**：`.claude/skills/microwave-spectroscopy-workflow/`

> 如需搭配通用论文读写、引用核验、审稿修回与 Origin 绘图技能，可同时安装通用包 [chem-materials-research-kit](https://github.com/qiransy/chem-materials-research-kit)。
