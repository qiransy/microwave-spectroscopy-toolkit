<div align="center">

<img src="pickett-runner/screenshots/pickett-icon.png" width="84" height="84" alt="Pickett Runner icon">

# Pickett Runner

**Iterative fitting, prediction, and run tracking for microwave rotational spectroscopy**

Windows desktop interface｜SPFIT + SPCAT｜Python standard library · Tkinter (zero third-party dependencies)

[简体中文](README.md) · English

</div>

**Pickett Runner** is the central tool of [`microwave-spectroscopy-toolkit`](https://github.com/qiransy/microwave-spectroscopy-toolkit), maintained by [qiransy](https://github.com/qiransy) to streamline iterative assignment workflows in gas-phase rotational spectroscopy. Manage experimental line lists and Hamiltonian models in a single window, run **SPFIT** and **SPCAT** back-to-back, archive input snapshots and fit diagnostics for every round, and publish updated `current.cat` predictions back to LLWP.

This repository also ships an open AI agent domain skill, [`microwave-spectroscopy-workflow`](skills/microwave-spectroscopy-workflow/SKILL.md), to assist with literature organization, conformer calculation summaries, and theory-vs-experiment checks.

## Real-world example

The screenshots show an actual assignment of the two-state tunneling system Homo-3. After 33 fitting rounds, the final fit includes 153 assigned transitions with a microwave RMS of **4.251 kHz**.

<div align="center">
  <img src="pickett-runner/screenshots/02-results.png" width="900" alt="Pickett Runner run history, summary metrics, and line-by-line residuals">
  <br>
  <sub>Run history and results. The table lists fitting rounds and publication status, while the lower panel shows summary metrics and an aligned residual report sorted by normalized residual.</sub>
</div>

## Key features

| Feature | Role in the assignment workflow |
| --- | --- |
| **Three modes & safe catalog publishing** | Run combined fit-and-predict, fit-only, or predict-only modes with independent `spfit.exe` / `spcat.exe` lookup. Combined runs feed the current round's fitted `VAR` into SPCAT; if prediction fails, the previous published `current.cat` remains intact. |
| **Working-copy editing & preflight checks** | Select `LIN`, `PAR`, `INT`, and `VAR` independently. Edit working copies to adjust PAR constraints, add parameters, or update INT frequency/J limits and temperature without altering original files; preflight checks inspect line diffs, duplicates, quantum-number counts, and `NLINE` capacity. |
| **Project isolation & full history tracking** | Archive numbered input snapshots, raw `FIT`, `VAR`, `CAT`, and logs per project directory; reuse fitted `PAR` and `VAR` from any round or restart from a previous round's inputs. |
| **Diagnostics & side-by-side comparison** | View line counts, microwave RMS (with kHz conversion), normalized RMS, and CAT totals in a summary strip; highlight large residuals and warnings; select two rounds with `Ctrl` to diff RMS and input files, then copy or export the summary. |
| **High-DPI layout & GitHub update info** | Built purely on the Python standard library with Windows high-DPI and 125% scaling support; includes an About & Updates dialog linking to repository docs, Issues, and on-demand GitHub version checks without affecting offline work. |

## Getting started

```text
Experimental spectrum + initial prediction → LLWP assignment → LIN → SPFIT fit → SPCAT prediction → current.cat → next assignment round
```

Line assignment works alongside **LLWP**. See the [official LLWP guide](https://llwp.astro.uni-koeln.de/docs.html) for installation, loading spectra and `CAT` predictions, and exporting `LIN` files; the software paper is [Bonah et al. (2022)](https://doi.org/10.1016/j.jms.2022.111674).

<div align="center">
  <img src="pickett-runner/screenshots/01-input.png" width="900" alt="Pickett Runner run modes, input files, and preflight summary">
  <br>
  <sub>Input configuration. Organized cards for input files, run options, and live preflight diagnostics, with the primary run button anchored at the top right.</sub>
</div>

1. Install Python 3.10 or later with Tkinter on Windows (no `pip install` needed).
2. Download or clone this repository and place separately obtained `spfit.exe` and `spcat.exe` in `pickett-runner/` (parent and grandparent directories are also searched when running from source).
3. Launch the script from that directory:

```shell
python pickett_runner.py
```

4. Choose a project directory and the required `LIN`, `PAR`, and `INT` files, check the preflight summary, and click the run button in the top-right corner.
5. Inspect RMS, line-by-line residuals, and fitted parameters in Run History & Results, then reload the updated `current.cat` in LLWP.

See the [Pickett Runner user guide](pickett-runner/README.en.md) for detailed usage and archive layout, or browse the [source code](pickett-runner/pickett_runner.py).

## AI Research Workflow Skill (Agent Skill)

This repository also includes an open-format AI agent domain skill, [`microwave-spectroscopy-workflow`](skills/microwave-spectroscopy-workflow/SKILL.md), designed to support:

- Literature search and [Zotero tagging](skills/microwave-spectroscopy-workflow/references/zotero-profile.md) for gas-phase rotational spectroscopy, molecular clusters, and microsolvation;
- Organizing CREST / Gaussian / ORCA conformer calculations while preserving original identifiers and energy conventions;
- Comparing calculated rotational constants, dipole components, and nuclear quadrupole tensors against SPFIT / SPCAT (Pickett Runner) fits;
- Progress reports, assignment evidence audits, and manuscript/figure presentation.

### Codex (project installation)

1. Download and extract this repository, or clone it with Git.
2. Copy the entire `skills/microwave-spectroscopy-workflow/` folder, including `references/`, into your project’s `.agents/skills/` directory. The resulting entry point is `<project>/.agents/skills/microwave-spectroscopy-workflow/SKILL.md`.
3. Open that project in Codex and start a new chat. Select `microwave-spectroscopy-workflow` from the skill picker. In the Codex CLI, use `/skills` to list skills.

For a first task, ask the skill to check the rotational-constant units, conformer identifiers, and energy conventions in a calculation summary. Running SPFIT / SPCAT requires the executables described above.

### Antigravity (plugin)

```shell
git clone https://github.com/qiransy/microwave-spectroscopy-toolkit.git ~/.gemini/config/plugins/microwave-spectroscopy-toolkit
```

See the [skill guide](skills/microwave-spectroscopy-workflow/README.md#codex) for copy commands and verification. For general chemistry and materials writing/plotting skills, pair it with [chem-materials-research-kit](https://github.com/qiransy/chem-materials-research-kit).

## About this repository

Pickett Runner and microwave rotational spectroscopy research workflows form the core of this repository, with supporting assignment notes and theoretical material added over time.

- Maintained by [qiransy](https://github.com/qiransy)
- Third-party programs: SPFIT and SPCAT were developed by H. M. Pickett. This repository provides the graphical companion source code and documentation only; obtain the original executables separately. See the [user guide](pickett-runner/README.en.md#references) for references.
