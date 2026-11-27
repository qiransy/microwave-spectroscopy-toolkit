<div align="center">

<img src="screenshots/pickett-icon.png" width="72" height="72" alt="Pickett Runner icon">

# Pickett Runner User Guide

[Repository home](../README.en.md) · [简体中文](README.md) · English

</div>

Pickett Runner is a lightweight Windows desktop interface for Pickett's SPFIT and SPCAT programs, built purely with the Python standard library and Tkinter (zero third-party dependencies) with high-DPI and 125% scaling support. The application interface is currently in Simplified Chinese and integrates smoothly with line-assignment tools such as LLWP.

## Run modes

| Mode | Required inputs | Purpose |
| --- | --- | --- |
| Fit and update prediction (拟合并更新预测谱) | LIN, PAR, INT | Run SPFIT, pass the fitted VAR directly to SPCAT, and generate an updated CAT file while preserving the last published `current.cat` if prediction fails. |
| Fit only (只拟合) | LIN, PAR | Obtain a fit report and updated model parameters. |
| Predict only (只预测) | VAR, INT | Calculate predictions from existing model parameters. |

## Installation and quick start

1. Install Python 3.10 or later with Tkinter on Windows.
2. Obtain SPFIT and SPCAT separately from their legitimate distribution source. Place `spfit.exe` and `spcat.exe` in this directory (parent and grandparent directories are also searched independently when running from source).
3. Launch the application:

```shell
python pickett_runner.py
```

Alternatively, use `pythonw.exe` to launch without a console window.

4. Select an existing project directory in the project bar and pick the `LIN`, `PAR`, `INT`, or `VAR` files required by the chosen mode.
5. Check the live preflight summary for line counts, diffs, duplicates, optional quantum-number checks, and `NLINE` capacity. Use the working-copy editor to adjust PAR constraints, add parameters, or change INT frequency limit (FQLIM), J limit (FEND), and temperature (TEMP).
6. Click the primary run button in the top-right corner. On completion, inspect the summary metrics strip, aligned line-by-line residuals, and fitted parameters in Run History and Results (记录与结果).
7. If automatic publication is enabled, load the updated `current.cat` in LLWP for the next assignment round.

See the [official LLWP guide](https://llwp.astro.uni-koeln.de/docs.html) for installation, loading spectra and line lists, and saving assignments.

## Screenshots

The example below shows actual iterative assignments for the two-state tunneling system Homo-3.

### Run and input settings

![Input configuration](screenshots/01-input.png)

The current project contains 153 line records and a 14-parameter model, with four quantum-number labels per energy level. The run button is anchored at the top right, and the preflight summary card reports live input checks.

### Run history and results

![Run history and detailed results](screenshots/02-results.png)

The history contains 33 fitting rounds, with a final microwave RMS of 4.251 kHz and a `★ current.cat` marker on the active published round. The metrics strip and detailed report display round 004; double-click a round to open its raw `FIT` report, or hold `Ctrl` to select two rounds to compare, copy, or export.

## Files and projects

- Each project keeps numbered input snapshots, fitting output, prediction files, and logs in its own run-history directory (`运行记录`).
- PAR and INT edits apply to working copies while preserving the original input files; unrun draft edits and notes can be saved across sessions.
- The history view supports reusing both fitted PAR and VAR from a successful round, restarting from a selected round's inputs, and comparing two fitting rounds (`Ctrl`-click) with one-click copy or export.
- Quantum-number count checking is optional; exact duplicate entries and same-frequency blends are reported in preflight checks.
- `current.cat` is updated atomically only after a successful prediction when publication is enabled, leaving the previous catalog intact on failure.
- The top-right About & Updates dialog links to the GitHub repository, online guide, and Issues, with on-demand background update checks that never block offline usage.

## Third-party programs

SPFIT and SPCAT were developed by H. M. Pickett. This repository contains the graphical companion tool source code and icon only. Obtain the original executables separately and consult the original program documentation for parameter codes and Hamiltonian definitions.

## References

H. M. Pickett, *The fitting and prediction of vibration-rotation spectra with spin interactions*, Journal of Molecular Spectroscopy **148**, 371–377 (1991).

L. Bonah, O. Zingsheim, H. S. P. Müller, J.-C. Guillemin, F. Lewen, S. Schlemmer, [*LLWP—A new Loomis-Wood software at the example of Acetone-13C1*](https://doi.org/10.1016/j.jms.2022.111674), Journal of Molecular Spectroscopy **388**, 111674 (2022).

Maintained by [qiransy](https://github.com/qiransy).
