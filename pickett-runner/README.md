# Pickett Runner

A lightweight Windows desktop interface for Pickett's SPFIT and SPCAT programs, intended for iterative rotational spectroscopy assignments. The interface is currently in Chinese.

## Features

- Run fitting, prediction or both in sequence.
- Select Pickett LIN, PAR, INT and VAR files independently.
- Edit working copies of PAR and INT without overwriting the source files.
- Save input snapshots, original reports and per-project run history.
- Inspect line residuals, RMS and parameter results.
- Refresh current.cat after successful prediction for use in tools such as LLWP.

## Screenshots

The screenshots below show an actual iterative assignment of the Homo-3 rotational spectrum, with two tunneling states.

**Input configuration** — 153 assigned lines, a 14-parameter model, and the option to update the prediction after SPFIT.

![Input configuration](screenshots/01-input.png)

**Run history and detailed results** — 33 fitting rounds, with the latest fit of 153 lines reaching a microwave RMS of 4.251 kHz. The detailed report shown is from round 004, illustrating line-by-line residuals, fitted parameters and the generated catalog.

![Run history and detailed results](screenshots/02-results.png)

## Quick start / 快速开始

1. Install Python 3.10 or later with Tkinter on Windows.
2. Obtain SPFIT and SPCAT separately from their legitimate distribution source. Place spfit.exe and spcat.exe beside pickett_runner.py (the parent directory is also supported for the existing installation layout).
3. Run `python pickett_runner.py` or use `pythonw.exe` to start without a console window.
4. Choose an existing project directory and the appropriate input files. Choose 拟合并更新预测谱 (fit and predict), 只拟合 (fit only), or 只预测 (predict only).
5. Inspect the results in 记录与结果 (run history and results). Successful predictions can update current.cat in the project directory.

每轮运行的输入快照和输出保存在项目内的“运行记录”目录，不覆盖初始输入。程序依据 Pickett 文件格式工作，可与 LLWP 等归属工具配合。

## Third-party programs

SPFIT and SPCAT are separate programs developed by H. M. Pickett. This repository contains the runner interface and does not redistribute those executables. Consult the original program documentation for parameter codes and model definitions.

## Citation

H. M. Pickett, *The fitting and prediction of vibration-rotation spectra with spin interactions*, Journal of Molecular Spectroscopy **148**, 371–377 (1991).

