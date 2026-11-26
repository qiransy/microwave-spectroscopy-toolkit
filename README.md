<div align="center">

# Pickett Runner

**微波转动光谱 · 一键拟合与预测**

Windows 图形化辅助工具｜SPFIT + SPCAT｜Python · Tkinter

简体中文 · [English](README.en.md)

</div>

Pickett Runner 由 [qiransy](https://github.com/qiransy) 开发，用于简化转动光谱中的迭代解谱流程。你可以在一个窗口中选择实验归属与模型文件、运行 SPFIT 拟合，再自动调用 SPCAT 生成新的预测谱，并将结果交回 LLWP 进行下一轮谱线归属。

## 实战展示

下面的界面来自 Homo-3 隧穿体系的实际解谱过程。经过 33 轮迭代，最终拟合 153 条归属谱线，微波 RMS 为 **4.251 kHz**。

<div align="center">
  <img src="pickett-runner/screenshots/02-results.png" width="900" alt="Pickett Runner 多轮拟合记录和逐线残差">
  <br>
  <sub>记录与结果界面。列表展示最近的拟合轮次，下方为第 004 轮的逐线拟合报告。</sub>
</div>

## 核心功能

| 功能 | 解谱中的用途 |
| --- | --- |
| **一键拟合与预测** | 支持 SPFIT → SPCAT 联合运行，也可单独拟合或预测。 |
| **模型与线表管理** | 独立选择 LIN、PAR、INT 和 VAR；编辑本轮参数副本。 |
| **项目隔离与历史记录** | 归档每轮输入、原始 FIT 报告、VAR 与 CAT，便于回溯和对比结果。 |
| **拟合结果检查** | 查看 RMS、逐线残差、参数及形式误差，辅助判断下一步拟合方向。 |
| **更新预测谱** | 预测成功后可刷新项目中的 current.cat，供 LLWP 下一轮归属使用。 |

## 如何使用

`实验谱 + 初始预测 → LLWP 归属 → LIN → SPFIT 拟合 → SPCAT 预测 → current.cat → 继续归属`

谱线归属使用 LLWP。安装、导入实验谱与 CAT 文件、导出 LIN 线表可参照 [LLWP 官方使用指南](https://llwp.astro.uni-koeln.de/docs.html)。软件论文见 [Bonah 等，2022](https://doi.org/10.1016/j.jms.2022.111674)。

<div align="center">
  <img src="pickett-runner/screenshots/01-input.png" width="900" alt="Pickett Runner 的 LIN、PAR、INT 输入配置">
  <br>
  <sub>运行与输入界面。选择归属线表、拟合模型及预测设置即可开始本轮计算。</sub>
</div>

1. 在 Windows 安装带有 Tkinter 的 Python 3.10 或更高版本。
2. 下载本仓库，将独立获取的 spfit.exe 和 spcat.exe 放在 pickett-runner 目录内。
3. 双击脚本或在该目录运行以下命令。

```shell
python pickett_runner.py
```

4. 在软件中选择项目目录与 LIN、PAR、INT 文件，运行「拟合并更新预测谱」。
5. 查看记录与结果，然后在 LLWP 中加载更新后的 current.cat。

进入 [Pickett Runner 使用说明](pickett-runner/README.md) 查看详细操作与文件管理方式，也可以直接 [查看源代码](pickett-runner/pickett_runner.py)。

## AI 科研工作流技能（Agent Skill）

本仓库同时内置了一套面向气相微波转动光谱的开放 AI Agent 领域技能 [`microwave-spectroscopy-workflow`](skills/microwave-spectroscopy-workflow/SKILL.md)，用于规范化辅助：

- 气相转动光谱、团簇与微溶剂化的文献调研与 [Zotero 标签管理](skills/microwave-spectroscopy-workflow/references/zotero-profile.md)；
- CREST / Gaussian / ORCA 构象计算结果整理（保留原始编号与能量口径，不替研究者擅自筛选候选）；
- 理论转动常数/偶极矩/核四极张量与 SPFIT/SPCAT（Pickett Runner）拟合结果的规范对照；
- 组会进展报告、论文指认证据边界审查与图表专业表达。

### Codex（项目级安装）

1. 下载并解压本仓库，或用 Git 克隆。
2. 将完整的 `skills/microwave-spectroscopy-workflow/` 文件夹复制到课题目录的 `.agents/skills/`，保留其中的 `references/`。最终入口为 `<课题目录>/.agents/skills/microwave-spectroscopy-workflow/SKILL.md`。
3. 在 Codex 中打开该课题目录并开启新对话，从 Skill 选择器选用 `microwave-spectroscopy-workflow`。CLI 中可用 `/skills` 查看。

可以先请 Codex 用这个 Skill 核对一份计算结果的转动常数单位、构象编号和能量口径。运行 SPFIT/SPCAT 仍需按上方说明单独准备程序。

### Antigravity（插件）

```shell
git clone https://github.com/qiransy/microwave-spectroscopy-toolkit.git ~/.gemini/config/plugins/microwave-spectroscopy-toolkit
```

复制命令和验证步骤见 [技能使用说明](skills/microwave-spectroscopy-workflow/README.md#codex)。如需搭配通用化学/材料论文读写与绘图技能，可配合使用 [chem-materials-research-kit](https://github.com/qiransy/chem-materials-research-kit)。

## 关于本仓库

本仓库以 Pickett Runner 为核心，后续会逐步加入与微波转动光谱相关的解谱实践、理论背景及学习资料，为软件的实际使用提供技术背景。

维护者：[qiransy](https://github.com/qiransy)

SPFIT 和 SPCAT 由 H. M. Pickett 开发。本仓库提供图形化辅助工具，原程序需要独立获取。相关文献信息见 [使用说明](pickett-runner/README.md#参考文献)。
