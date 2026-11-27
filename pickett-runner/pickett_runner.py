"""Windows desktop front end for Pickett SPFIT / SPCAT (standard library only)."""
import ctypes
import difflib
import json
import math
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unicodedata
import urllib.error
import urllib.request
import webbrowser
from collections import Counter
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, simpledialog, ttk


VERSION = "v1.1.0"
REPO_OWNER = "qiransy"
REPO_NAME = "microwave-spectroscopy-toolkit"
REPO_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}"
DOCS_URL = f"{REPO_URL}/blob/main/pickett-runner/README.md"
ISSUES_URL = f"{REPO_URL}/issues"
API_REPO_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"
API_RELEASE_URL = f"{API_REPO_URL}/releases/latest"
API_COMMITS_URL = f"{API_REPO_URL}/commits?per_page=1"

APP_DIR = Path(__file__).resolve().parent
try:
    BUILD_INFO = json.loads((APP_DIR / "build-info.json").read_text(encoding="utf-8"))
    if not all(isinstance(BUILD_INFO[k], str) for k in ("source_sha256", "git_base")):
        BUILD_INFO = {}
except (OSError, ValueError, TypeError, KeyError):
    BUILD_INFO = {}
PREFS = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "PickettRunner" / (
    "review-projects.json" if BUILD_INFO.get("review") else "projects.json"
)
MODES = ("拟合并更新预测谱", "只拟合", "只预测")
RUN_LABELS = ("▶ 拟合并更新预测谱", "▶ 开始拟合", "▶ 生成预测谱")
LABELS = {"lin": "实验归属 LIN", "par": "拟合模型 PAR", "int": "预测设置 INT", "var": "预测参数 VAR"}
REQUIRED = (("lin", "par", "int"), ("lin", "par"), ("var", "int"))
PROGRAMS = (("spfit.exe", "spcat.exe"), ("spfit.exe",), ("spcat.exe",))
NUM = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][-+]?\d+)?"

THEME = {
    "bg": "#F3F5F8",
    "surface": "#FFFFFF",
    "surface_alt": "#F8FAFC",
    "border": "#DCE3EC",
    "border_strong": "#C3CEDD",
    "text": "#1E293B",
    "muted": "#64748B",
    "accent": "#2563EB",
    "accent_hover": "#1D4ED8",
    "accent_soft": "#EFF6FF",
    "accent_border": "#BFDBFE",
    "success": "#15803D",
    "success_bg": "#ECFDF5",
    "warn": "#B45309",
    "warn_bg": "#FFFBEB",
    "danger": "#B91C1C",
    "danger_bg": "#FEF2F2",
    "zebra": "#F8FAFC",
}


def enable_dpi_awareness():
    if sys.platform == "win32":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass


def decode(data):
    for encoding in ("utf-8-sig", "gb18030", "cp1252"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            pass
    return data.decode("latin1"), "latin1"


def read(path):
    return decode(Path(path).read_bytes())[0]


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as f:
        tmp = Path(f.name)
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def dump(path, obj):
    atomic(path, json.dumps(obj, ensure_ascii=False, indent=2).encode("utf8"))


def display_width(text):
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def pad_left(text, width):
    return " " * max(0, width - display_width(text)) + text


def pad_right(text, width):
    return text + " " * max(0, width - display_width(text))


def executable_paths(mode, bindir=None):
    if bindir is not None:
        directories = (Path(bindir).resolve(),)
    elif getattr(sys, "frozen", False):
        directories = (APP_DIR / "pickett-bin",)
    else:
        directories = (APP_DIR, APP_DIR.parent, APP_DIR.parent.parent)

    found = {}
    missing = []
    for name in PROGRAMS[mode]:
        candidate = next((d / name for d in directories if (d / name).is_file()), None)
        if candidate is None:
            missing.append(name)
        else:
            found[name] = candidate
    if missing:
        locations = "、".join(map(str, directories))
        raise ValueError(f"缺少 {'、'.join(missing)}。已检查：{locations}")
    return found


def pickett_float(value):
    return float(value.replace("D", "E").replace("d", "e"))


def build_source():
    if not BUILD_INFO:
        return "本地源码"
    kind = "本地验收构建" if BUILD_INFO.get("review") else "本地构建"
    return f"{kind} · 源码 SHA-256 {BUILD_INFO['source_sha256'][:12]} · Git 基线 {BUILD_INFO['git_base'][:12]}"


def version_tuple(tag):
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:\+[0-9A-Za-z.-]+)?", str(tag or ""), re.I)
    return tuple(map(int, m.groups())) if m else None


def fetch_github_info(timeout=6):
    headers = {
        "User-Agent": f"PickettRunner/{VERSION}",
        "Accept": "application/vnd.github+json",
    }

    def get_json(url):
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    info = {"repo_url": REPO_URL, "build_source": build_source()}
    repo = get_json(API_REPO_URL)
    info["description"] = repo.get("description") or ""
    info["stars"] = repo.get("stargazers_count", 0)
    info["updated_at"] = (repo.get("pushed_at") or repo.get("updated_at") or "")[:10]

    try:
        rel = get_json(API_RELEASE_URL)
        tag = rel.get("tag_name") or ""
        info["release_tag"] = tag
        info["release_name"] = rel.get("name") or tag
        info["release_url"] = rel.get("html_url") or REPO_URL
        info["release_date"] = (rel.get("published_at") or "")[:10]
        info["release_notes"] = (rel.get("body") or "").strip()
        latest_version, local_version = version_tuple(tag), version_tuple(VERSION)
        info["has_update"] = bool(
            latest_version and local_version and not rel.get("draft") and not rel.get("prerelease")
            and latest_version > local_version
        )
        info["release_status"] = (
            "发现新版本！" if info["has_update"] else
            "版本标签不可比较。" if not latest_version or not local_version else
            "与当前版本号相同。" if latest_version == local_version else
            "暂无更高的正式发布版。"
        )
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        commits = get_json(API_COMMITS_URL)
        latest = commits[0] if commits else {}
        commit_obj = latest.get("commit") or {}
        info["release_tag"] = ""
        info["commit_sha"] = (latest.get("sha") or "")[:7]
        info["commit_msg"] = (commit_obj.get("message") or "").splitlines()[0] if commit_obj.get("message") else ""
        info["commit_date"] = ((commit_obj.get("committer") or {}).get("date") or "")[:10]
        info["release_url"] = latest.get("html_url") or REPO_URL
        info["has_update"] = False
    return info


def records(data, nq=0):
    rows = [s for s in decode(data)[0].splitlines() if s.strip()]
    if not rows:
        raise ValueError("LIN 中没有记录。")
    keys, freq = [], {}
    for n, line in enumerate(rows, 1):
        q = line[:36]
        fields = [q[i:i + 3].strip() for i in range(0, 36, 3)]
        if nq and sum(bool(x) for x in fields) != 2 * nq:
            raise ValueError(f"LIN 第 {n} 行与每态 {nq} 个量子数不符。请检查空白格。")
        keys.append(" ".join(line.split()))
        tail = line[36:].split()
        if tail:
            freq.setdefault(tail[0], set()).add(q)
    repeats = {key: count for key, count in Counter(keys).items() if count > 1}
    blends = [f for f, qs in freq.items() if len(qs) > 1]
    return rows, repeats, blends


def reserve(root, note):
    root.mkdir(parents=True, exist_ok=True)
    nums = [int(m[1]) for p in root.iterdir() if (m := re.match(r"^(\d+)_", p.name))]
    n = max(nums, default=0) + 1
    slug = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", note).strip(" .")[:50] or "运行"
    while True:
        path = root / f"{n:03d}_{slug}"
        try:
            path.mkdir()
            return path
        except FileExistsError:
            n += 1


def invoke(exe, cwd):
    with (cwd / "运行.log").open("wb") as log:
        p = subprocess.run(
            [str(exe), "model"],
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    if p.returncode:
        raise RuntimeError(f"{exe.name} 退出码 {p.returncode}。详见 {cwd.name}/运行.log")
    return read(cwd / "运行.log")


def fit_summary(report):
    rms = re.findall(r"MICROWAVE RMS\s*=\s*(" + NUM + r")", report)
    norm = re.findall(r"OLD, NEW RMS ERROR=\s*" + NUM + r"\s+(" + NUM + r")", report)
    block = report.rsplit("EXP.FREQ.", 1)[-1].split("NORMALIZED DIAGONAL")[0]
    residuals = []
    for line in block.splitlines():
        if not re.match(r"\s*\d+:", line):
            continue
        # The quantum-number fields are followed by decimal-valued frequencies.
        m = re.match(r"\s*(\d+):\s*(.*?)\s+([-+]?\d+\.\d+)\s+(" + NUM + r")\s+(" + NUM + r")\s+(" + NUM + r")", line)
        if m:
            i, q, obs, calc, diff, err = m.groups()
            residuals.append((i, q.strip(), obs, calc, diff, err))
    params = (
        report.rsplit("CHANGE THIS ITERATION", 1)[-1].split("MICROWAVE AVG")[0].strip()
        if "CHANGE THIS ITERATION" in report
        else ""
    )
    alerts = [s.strip() for s in report.splitlines() if re.search(r"warn|reject|singular|diverg|overflow", s, re.I)]
    return dict(
        rms=rms[-1] if rms else "",
        norm=norm[-1] if norm else "",
        residuals=residuals,
        parameters=params,
        alerts=list(dict.fromkeys(alerts))[-25:],
    )


def ensure_line_capacity(data, required):
    # SPFIT writes NLINE back as the actual count. A continued fit can have more lines.
    raw = data.splitlines(keepends=True)
    if len(raw) < 2:
        raise ValueError("PAR 缺少第二行控制参数。")
    m = re.match(rb"^\s*[+-]?\d+[ \t,]+([+-]?\d+)(?=[ \t,\r\n/]|$)", raw[1])
    if m:
        old = int(m[1])
        if 0 < abs(old) < required:
            new = required if old > 0 else -required
            raw[1] = raw[1][: m.start(1)] + str(new).encode("ascii") + raw[1][m.end(1) :]
            return b"".join(raw), f"本轮 LIN 有 {required} 条，工作副本 NLINE 从 {old} 扩至 {new}。"
    return data, ""


def execute(project, mode, note, paths, inputs, publish, nq=0, bindir=None):
    programs = executable_paths(mode, bindir)
    folder = reserve(project / "运行记录", note)
    meta = dict(
        mode=MODES[mode],
        note=note,
        sources=paths,
        time=datetime.now().isoformat(timespec="seconds"),
        status="运行中",
        published=False,
    )
    state = folder / "记录.json"
    dump(state, meta)
    snap = folder / "输入"
    try:
        snap.mkdir()
        for k, data in inputs.items():
            (snap / ("model." + k)).write_bytes(data)
        if mode != 2:
            rows, repeats, blends = records(inputs["lin"], nq)
            meta.update(lines=len(rows), repeats=repeats, same_frequency=blends)
            fit = folder / "拟合"
            fit.mkdir()
            for k in ("par", "lin"):
                shutil.copyfile(snap / ("model." + k), fit / ("model." + k))
            par_data, capacity = ensure_line_capacity(inputs["par"], len(rows))
            if capacity:
                (fit / "model.par").write_bytes(par_data)
                meta["capacity"] = capacity
            log = invoke(programs["spfit.exe"], fit)
            report = read(fit / "model.fit")
            if "FIT COMPLETE" not in (report + log).upper() or not (fit / "model.var").stat().st_size:
                raise RuntimeError("SPFIT 未确认完成。请查看本轮原始报告及日志。")
            meta.update(fit_summary(report))
            meta["fit_ok"] = True
        if mode != 1:
            pred = folder / "预测"
            pred.mkdir()
            shutil.copyfile(snap / "model.int", pred / "model.int")
            shutil.copyfile((snap if mode == 2 else fit) / "model.var", pred / "model.var")
            log = invoke(programs["spcat.exe"], pred)
            cat = pred / "model.cat"
            with cat.open("rb") as f:
                count = 0
                for row in f:
                    if not row.strip():
                        continue
                    if len(row.rstrip(b"\r\n")) < 55 or not math.isfinite(float(row[:13])):
                        raise RuntimeError("CAT 中存在无效记录。")
                    count += 1
            if not count or re.search(r"(?im)^\s*(?:fatal|error\b)", log):
                raise RuntimeError("SPCAT 未生成有效预测。请查看 OUT 和日志。")
            meta["cat_lines"] = count
            if publish:
                atomic(project / "current.cat", cat.read_bytes())
                meta["published"] = True
        meta["status"] = "完成"
    except Exception as e:
        meta.update(status="失败", error=str(e))
    dump(state, meta)
    return folder, meta


def runs(project):
    result = []
    for f in (project / "运行记录").glob("*/记录.json"):
        if not re.match(r"^\d+_", f.parent.name):
            continue
        try:
            meta = json.loads(f.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        if isinstance(meta, dict) and {"mode", "status", "time", "sources"} <= meta.keys():
            result.append((f.parent, meta))
    return sorted(result, key=lambda r: int(r[0].name.split("_")[0]), reverse=True)


def format_rms_khz(rms_str):
    try:
        val = pickett_float(str(rms_str))
    except (TypeError, ValueError):
        return ""
    return f"{val * 1000:.3f} kHz"


def describe(folder, meta):
    out = [f"■ {folder.name}", f"运行方式：{meta['mode']}   状态：{meta['status']}   时间：{meta['time']}"]
    if meta.get("error"):
        out.append(f"[错误] {meta['error']}")
    if meta.get("fit_ok"):
        if meta.get("capacity"):
            out.append(f"[提示] {meta['capacity']}")
        rms_khz = format_rms_khz(meta.get("rms", ""))
        rms_disp = f"{meta['rms']} MHz（{rms_khz}）" if rms_khz else f"{meta['rms']} MHz"
        out += [
            f"输入谱线：{meta['lines']} 条   微波 RMS：{rms_disp}   归一化 RMS：{meta['norm']}",
            "",
            "逐线结果（按 |残差/误差| 降序；负输入误差的红外线见原报告）",
        ]
        q_width = max([22] + [display_width(v[1]) for v in meta["residuals"] if pickett_float(v[5]) > 0])
        header = (
            f"{pad_left('序号', 4)}  {pad_right('量子数', q_width)}  "
            f"{pad_left('实测 / MHz', 13)}  {pad_left('计算 / MHz', 13)}  "
            f"{pad_left('残差 / kHz', 11)}  {pad_left('误差 / kHz', 10)}  {pad_left('残差/误差', 10)}"
        )
        out.append(header)
        out.append("-" * display_width(header))
        ordered = sorted(
            meta["residuals"],
            key=lambda v: abs(pickett_float(v[4]) / pickett_float(v[5])) if pickett_float(v[5]) else 0,
            reverse=True,
        )
        for i, q, o, c, d, e in ordered:
            ef = pickett_float(e)
            if ef > 0:
                df = pickett_float(d)
                out.append(
                    f"{i:>4}  {pad_right(q, q_width)}  "
                    f"{o:>13}  {c:>13}  "
                    f"{1000 * df:>11.2f}  {1000 * ef:>10.2f}  {df / ef:>10.2f}"
                )
        out += ["", "参数结果（数值、形式误差、本次迭代变化量）", meta["parameters"]]
        if meta.get("alerts"):
            out += ["", "拟合警告 / 提醒"]
            out.extend(meta["alerts"])
    if "cat_lines" in meta:
        out += [
            "",
            f"预测谱 CAT：{meta['cat_lines']} 条   " + ("已发布至 current.cat" if meta["published"] else "仅归档"),
        ]
    out += ["", "输入来源（本轮实际内容见“输入”快照）"] + [f"  {k.upper():<4}  {v}" for k, v in meta["sources"].items()]
    return "\n".join(out)


class Window:
    def __init__(self, root):
        self.root = root
        root.title("Pickett Runner | 微波转动光谱拟合与预测")
        root.geometry("1080x780")
        root.minsize(900, 660)
        root.configure(bg=THEME["bg"])

        try:
            self.pref = json.loads(PREFS.read_text(encoding="utf8"))
        except (OSError, ValueError):
            self.pref = {}
        if saved_geo := self.pref.get("geometry"):
            try:
                root.geometry(saved_geo)
            except tk.TclError:
                pass

        self.mono_font = self._pick_mono_font()
        self._configure_styles()

        self.project = tk.StringVar()
        self.mode = tk.StringVar(value=MODES[0])
        self.paths = {k: tk.StringVar() for k in LABELS}
        self.filelabels = {k: tk.StringVar() for k in LABELS}
        self.fullpaths = tk.BooleanVar()
        self.project_name = tk.StringVar(value="未选择项目")
        self.result_dir = tk.StringVar()
        self.history_title = tk.StringVar()
        self.check_qn = tk.BooleanVar()
        self.qn_hint = tk.StringVar()
        self.draft_hint = tk.StringVar()
        self.edits = {}
        self.nq = tk.IntVar(value=0)
        self.publish = tk.BooleanVar(value=True)
        self.note = tk.StringVar()
        self.status = tk.StringVar()
        self.pending = queue.Queue()
        self.busy = False
        self.items = []
        self.edit_buttons = {}
        self.metric_vars = {k: tk.StringVar(value="—") for k in ("lines", "rms", "norm", "cat", "state")}
        self.metric_labels = {}

        self._build_layout()
        self.load_project(self.pref.get("last", ""))
        root.protocol("WM_DELETE_WINDOW", self.close)

    @staticmethod
    def _pick_mono_font():
        families = set(tkfont.families())
        for name in ("Cascadia Mono", "Consolas", "Courier New"):
            if name in families:
                return name
        return "TkFixedFont"

    def _configure_styles(self):
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        ui = ("Microsoft YaHei UI", 9)
        ui_bold = ("Microsoft YaHei UI", 9, "bold")
        ui_title = ("Microsoft YaHei UI", 10, "bold")

        style.configure(".", background=THEME["bg"], foreground=THEME["text"], font=ui)
        style.configure("TFrame", background=THEME["bg"])
        style.configure("Header.TFrame", background=THEME["surface"])
        style.configure("Card.TFrame", background=THEME["surface"])
        style.configure("Subtle.TFrame", background=THEME["surface_alt"])
        style.configure("Status.TFrame", background=THEME["surface"])

        style.configure("TLabel", background=THEME["bg"], foreground=THEME["text"], font=ui)
        style.configure("Header.TLabel", background=THEME["surface"], foreground=THEME["text"], font=ui)
        style.configure("AppTitle.TLabel", background=THEME["surface"], foreground=THEME["text"], font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("CardTitle.TLabel", background=THEME["surface"], foreground=THEME["text"], font=ui_title)
        style.configure("Card.TLabel", background=THEME["surface"], foreground=THEME["text"], font=ui)
        style.configure("Muted.TLabel", background=THEME["surface"], foreground=THEME["muted"], font=ui)
        style.configure("MutedBg.TLabel", background=THEME["bg"], foreground=THEME["muted"], font=ui)
        style.configure("Draft.TLabel", background=THEME["bg"], foreground=THEME["warn"], font=ui_bold)
        style.configure("Status.TLabel", background=THEME["surface"], foreground=THEME["muted"], font=("Microsoft YaHei UI", 8))

        style.configure("MetricKey.TLabel", background=THEME["surface_alt"], foreground=THEME["muted"], font=("Microsoft YaHei UI", 8))
        style.configure("MetricVal.TLabel", background=THEME["surface_alt"], foreground=THEME["text"], font=(self.mono_font, 10, "bold"))

        style.configure("TSeparator", background=THEME["border"])

        style.configure(
            "TButton",
            background=THEME["surface"],
            foreground=THEME["text"],
            bordercolor=THEME["border_strong"],
            lightcolor=THEME["surface"],
            darkcolor=THEME["surface"],
            focuscolor=THEME["accent_soft"],
            borderwidth=1,
            relief="solid",
            padding=(11, 5),
            font=ui,
        )
        style.map(
            "TButton",
            background=[("active", THEME["surface_alt"]), ("pressed", "#E8EEF6"), ("disabled", THEME["surface_alt"])],
            bordercolor=[("active", THEME["accent"]), ("disabled", THEME["border"])],
            foreground=[("disabled", THEME["muted"])],
        )

        style.configure(
            "Accent.TButton",
            background=THEME["accent"],
            foreground="#FFFFFF",
            bordercolor=THEME["accent"],
            lightcolor=THEME["accent"],
            darkcolor=THEME["accent"],
            focuscolor=THEME["accent"],
            borderwidth=1,
            relief="solid",
            padding=(18, 7),
            font=ui_bold,
        )
        style.map(
            "Accent.TButton",
            background=[("active", THEME["accent_hover"]), ("pressed", "#1E40AF"), ("disabled", "#94A3B8")],
            bordercolor=[("active", THEME["accent_hover"]), ("disabled", "#94A3B8")],
            foreground=[("disabled", "#F8FAFC")],
        )

        style.configure(
            "Edited.TButton",
            background=THEME["warn_bg"],
            foreground=THEME["warn"],
            bordercolor="#F59E0B",
            lightcolor=THEME["warn_bg"],
            darkcolor=THEME["warn_bg"],
            focuscolor=THEME["warn_bg"],
            borderwidth=1,
            relief="solid",
            padding=(11, 5),
            font=ui_bold,
        )
        style.map("Edited.TButton", background=[("active", "#FEF3C7")])

        style.configure(
            "Ghost.TButton",
            background=THEME["surface"],
            foreground=THEME["accent"],
            bordercolor=THEME["accent_border"],
            lightcolor=THEME["surface"],
            darkcolor=THEME["surface"],
            focuscolor=THEME["accent_soft"],
            borderwidth=1,
            relief="solid",
            padding=(10, 4),
            font=ui,
        )
        style.map("Ghost.TButton", background=[("active", THEME["accent_soft"])])

        style.configure(
            "Card.TRadiobutton",
            background=THEME["surface"],
            foreground=THEME["text"],
            indicatorcolor=THEME["surface"],
            focuscolor=THEME["surface"],
            font=ui,
        )
        style.map("Card.TRadiobutton", indicatorcolor=[("selected", THEME["accent"])])

        style.configure(
            "Card.TCheckbutton",
            background=THEME["surface"],
            foreground=THEME["text"],
            focuscolor=THEME["surface"],
            font=ui,
        )
        unchecked = tk.PhotoImage(master=self.root, width=18, height=14)
        unchecked.put(THEME["border_strong"], to=(0, 0, 14, 14))
        unchecked.put(THEME["surface"], to=(1, 1, 13, 13))
        checked = tk.PhotoImage(master=self.root, width=18, height=14)
        checked.put(THEME["accent"], to=(0, 0, 14, 14))
        for x, y in ((3, 7), (4, 8), (5, 9), (6, 8), (7, 7), (8, 6), (9, 5), (10, 4)):
            checked.put(THEME["surface"], to=(x, y, x + 1, y + 2))
        self.check_indicators = (unchecked, checked)
        style.element_create("Pickett.Checkbutton.indicator", "image", unchecked, ("selected", checked), sticky="")
        style.layout("Card.TCheckbutton", [
            ("Checkbutton.padding", {"sticky": "nswe", "children": [
                ("Pickett.Checkbutton.indicator", {"side": "left", "sticky": ""}),
                ("Checkbutton.focus", {"side": "left", "sticky": "w", "children": [
                    ("Checkbutton.label", {"sticky": "nswe"}),
                ]}),
            ]}),
        ])

        style.configure(
            "TEntry",
            fieldbackground=THEME["surface"],
            foreground=THEME["text"],
            bordercolor=THEME["border_strong"],
            lightcolor=THEME["surface"],
            darkcolor=THEME["surface"],
            padding=(7, 5),
        )
        style.map(
            "TEntry",
            fieldbackground=[("readonly", THEME["surface_alt"])],
            bordercolor=[("focus", THEME["accent"])],
        )

        style.configure(
            "TSpinbox",
            fieldbackground=THEME["surface"],
            background=THEME["surface_alt"],
            foreground=THEME["text"],
            bordercolor=THEME["border_strong"],
            arrowcolor=THEME["text"],
            padding=(5, 3),
        )

        style.configure("TNotebook", background=THEME["bg"], borderwidth=0, tabmargins=(0, 0, 0, 0))
        style.configure(
            "TNotebook.Tab",
            background="#E5EAF1",
            foreground=THEME["muted"],
            bordercolor=THEME["border"],
            lightcolor="#E5EAF1",
            darkcolor="#E5EAF1",
            padding=(16, 7),
            font=ui_bold,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", THEME["surface"]), ("active", "#EEF2F7")],
            foreground=[("selected", THEME["accent"]), ("active", THEME["text"])],
            lightcolor=[("selected", THEME["surface"])],
            darkcolor=[("selected", THEME["surface"])],
            expand=[("selected", (0, 2, 0, 0))],
        )

        style.configure(
            "Treeview",
            background=THEME["surface"],
            fieldbackground=THEME["surface"],
            foreground=THEME["text"],
            bordercolor=THEME["border"],
            lightcolor=THEME["border"],
            darkcolor=THEME["border"],
            rowheight=27,
            font=ui,
        )
        style.configure(
            "Treeview.Heading",
            background=THEME["surface_alt"],
            foreground=THEME["muted"],
            bordercolor=THEME["border"],
            lightcolor=THEME["surface_alt"],
            darkcolor=THEME["surface_alt"],
            relief="flat",
            padding=(8, 6),
            font=ui_bold,
        )
        style.map(
            "Treeview",
            background=[("selected", THEME["accent_soft"])],
            foreground=[("selected", THEME["text"])],
        )
        style.map("Treeview.Heading", background=[("active", "#EDF2F7")])

        style.configure("TPanedwindow", background=THEME["bg"])
        style.configure("Sash", sashthickness=6, gripcount=0, background=THEME["bg"])

        style.configure(
            "Vertical.TScrollbar",
            background="#CBD5E1",
            troughcolor=THEME["surface_alt"],
            bordercolor=THEME["surface_alt"],
            arrowcolor=THEME["muted"],
            lightcolor="#CBD5E1",
            darkcolor="#CBD5E1",
        )
        style.configure(
            "Horizontal.TScrollbar",
            background="#CBD5E1",
            troughcolor=THEME["surface_alt"],
            bordercolor=THEME["surface_alt"],
            arrowcolor=THEME["muted"],
            lightcolor="#CBD5E1",
            darkcolor="#CBD5E1",
        )

    def _card(self, parent, title=None, right_widget_fn=None, pad=(14, 12)):
        outer = tk.Frame(parent, bg=THEME["surface"], highlightbackground=THEME["border"], highlightthickness=1)
        body = ttk.Frame(outer, style="Card.TFrame", padding=pad)
        body.pack(fill="both", expand=True)
        if title or right_widget_fn:
            head = ttk.Frame(body, style="Card.TFrame")
            head.pack(fill="x", pady=(0, 8))
            if title:
                ttk.Label(head, text=title, style="CardTitle.TLabel").pack(side="left")
            if right_widget_fn:
                right_widget_fn(head)
        content = ttk.Frame(body, style="Card.TFrame")
        content.pack(fill="both", expand=True)
        return outer, content

    def _build_layout(self):
        # Top application header
        header_wrap = tk.Frame(self.root, bg=THEME["surface"])
        header_wrap.pack(fill="x")
        header = ttk.Frame(header_wrap, style="Header.TFrame", padding=(16, 10, 16, 7))
        header.pack(fill="x")
        brand = ttk.Frame(header, style="Header.TFrame")
        brand.pack(side="left")
        ttk.Label(brand, text="Pickett Runner", style="AppTitle.TLabel").pack(side="left")
        ttk.Button(header, text="关于与更新", style="Ghost.TButton", command=self.show_about).pack(side="right")
        tk.Frame(header_wrap, bg=THEME["border"], height=1).pack(fill="x")

        project_bar = ttk.Frame(header_wrap, style="Header.TFrame", padding=(16, 6, 16, 8))
        project_bar.pack(fill="x")
        ttk.Button(project_bar, text="切换项目…", command=self.choose_project).pack(side="right", padx=(10, 0))
        ttk.Label(project_bar, textvariable=self.project_name, style="CardTitle.TLabel", width=24).pack(side="left", padx=(0, 8))
        proj_entry = ttk.Entry(project_bar, textvariable=self.result_dir, state="readonly")
        proj_entry.pack(side="left", fill="x", expand=True)
        tk.Frame(header_wrap, bg=THEME["border"], height=1).pack(fill="x")

        # Main workspace
        workspace = ttk.Frame(self.root, padding=(14, 10, 14, 8))
        workspace.pack(fill="both", expand=True)

        self.tabs = ttk.Notebook(workspace)
        self.tabs.pack(fill="both", expand=True)

        self.main = ttk.Frame(self.tabs, padding=(12, 12, 12, 10))
        self.hist = ttk.Frame(self.tabs, padding=(12, 10, 12, 10))
        self.tabs.add(self.main, text="  运行与输入  ")
        self.tabs.add(self.hist, text="  记录与结果  ")

        self._build_run_tab()
        self._build_history_tab()

        # Bottom status bar
        status_wrap = tk.Frame(self.root, bg=THEME["surface"])
        status_wrap.pack(fill="x", side="bottom", before=workspace)
        tk.Frame(status_wrap, bg=THEME["border"], height=1).pack(fill="x")
        status_bar = ttk.Frame(status_wrap, style="Status.TFrame", padding=(14, 5))
        status_bar.pack(fill="x")
        ttk.Label(status_bar, textvariable=self.status, style="Status.TLabel").pack(side="left")

    def _build_run_tab(self):
        actions = ttk.Frame(self.main)
        actions.pack(fill="x", pady=(0, 8))
        self.go = ttk.Button(actions, text=RUN_LABELS[0], style="Accent.TButton", command=self.start)
        self.go.pack(side="right")
        ttk.Label(actions, textvariable=self.draft_hint, style="Draft.TLabel").pack(side="left")

        # Card 1: Mode & Input files
        def mode_right(parent):
            ttk.Checkbutton(
                parent,
                text="显示完整路径",
                variable=self.fullpaths,
                style="Card.TCheckbutton",
                command=self.refresh,
            ).pack(side="right")

        card1, c1 = self._card(self.main, "1. 运行方式与输入文件", right_widget_fn=mode_right)
        card1.pack(fill="x", pady=(0, 10))
        c1.columnconfigure(1, weight=1)

        switches = ttk.Frame(c1, style="Card.TFrame")
        switches.grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 10))
        ttk.Label(switches, text="运行模式：", style="Muted.TLabel").pack(side="left", padx=(0, 6))
        for label in MODES:
            ttk.Radiobutton(
                switches,
                text=label,
                variable=self.mode,
                value=label,
                style="Card.TRadiobutton",
                command=self.refresh,
            ).pack(side="left", padx=(0, 16))

        self.controls = {}
        for i, (k, label) in enumerate(LABELS.items(), 1):
            title = ttk.Label(c1, text=label, style="Card.TLabel", width=13)
            title.grid(row=i, column=0, sticky="w", pady=5)
            entry = ttk.Entry(c1, textvariable=self.filelabels[k], state="readonly")
            entry.grid(row=i, column=1, sticky="ew", padx=(4, 8), pady=5)
            browse = ttk.Button(c1, text="浏览…", command=lambda k=k: self.browse(k))
            browse.grid(row=i, column=2, pady=5)
            edit = None
            if k in ("par", "int"):
                edit = ttk.Button(c1, text="编辑本轮副本", command=lambda k=k: self.editor(k))
                edit.grid(row=i, column=3, padx=(6, 0), pady=5)
                self.edit_buttons[k] = edit
            self.controls[k] = [w for w in (title, entry, browse, edit) if w is not None]

        self.continue_row = ttk.Frame(c1, style="Card.TFrame")
        self.continue_row.grid(row=5, column=1, columnspan=3, sticky="w", padx=(4, 0), pady=(6, 0))
        self.continue_button = ttk.Button(self.continue_row, text="沿用最近成功拟合的参数", command=self.latest)
        self.continue_button.pack(side="left")

        # Card 2: Note & validation options
        card2, c2 = self._card(self.main, "2. 本轮备注与选项")
        card2.pack(fill="x", pady=(0, 10))
        c2.columnconfigure(1, weight=1)

        ttk.Label(c2, text="本轮备注", style="Card.TLabel", width=13).grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(c2, textvariable=self.note).grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=(0, 8))

        self.qn_box = ttk.Frame(c2, style="Card.TFrame")
        self.qn_box.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ttk.Checkbutton(
            self.qn_box,
            text="检查每条跃迁的量子数个数",
            variable=self.check_qn,
            style="Card.TCheckbutton",
            command=self.refresh,
        ).pack(side="left")
        self.qn_options = ttk.Frame(self.qn_box, style="Card.TFrame")
        self.qn_options.pack(side="left", padx=(12, 0))
        ttk.Label(self.qn_options, text="每个能级", style="Card.TLabel").pack(side="left")
        ttk.Spinbox(
            self.qn_options,
            from_=1,
            to=6,
            width=3,
            textvariable=self.nq,
            state="readonly",
            command=self.refresh,
        ).pack(side="left", padx=4)
        ttk.Label(self.qn_options, textvariable=self.qn_hint, style="Muted.TLabel").pack(side="left")
        ttk.Button(
            self.qn_box,
            text="怎么选？",
            style="Ghost.TButton",
            command=lambda: messagebox.showinfo(
                "量子数个数",
                "按一个能级实际使用的标签计数。例如 J、Ka、Kc 共 3 项；再加内部态标签 v，就是 4 项。"
                "超精细结构按实际耦合标签计数。\n此项只核对每行填写的总数。重复记录始终单独检查。",
            ),
        ).pack(side="right")

        self.publish_row = ttk.Frame(c2, style="Card.TFrame")
        self.publish_row.grid(row=2, column=0, columnspan=2, sticky="w")
        self.publish_button = ttk.Checkbutton(
            self.publish_row,
            text="预测成功后自动更新项目根目录中的 current.cat（供 LLWP 读取）",
            variable=self.publish,
            style="Card.TCheckbutton",
        )
        self.publish_button.pack(side="left")

        # Card 3: Live preflight summary (fills remaining vertical space cleanly)
        def precheck_right(parent):
            ttk.Button(parent, text="重新检查输入", command=self.refresh).pack(side="right")

        card3, c3 = self._card(self.main, "3. 输入预检摘要", right_widget_fn=precheck_right)
        card3.pack(fill="both", expand=True, pady=(0, 10))
        self.preview_box = tk.Text(
            c3,
            height=6,
            wrap="word",
            relief="flat",
            bg=THEME["surface_alt"],
            fg=THEME["text"],
            highlightbackground=THEME["border"],
            highlightthickness=1,
            padx=10,
            pady=8,
            font=("Microsoft YaHei UI", 9),
            state="disabled",
        )
        preview_scroll = ttk.Scrollbar(c3, orient="vertical", command=self.preview_box.yview)
        preview_scroll.pack(side="right", fill="y")
        self.preview_box.configure(yscrollcommand=preview_scroll.set)
        self.preview_box.pack(side="left", fill="both", expand=True)
        self.preview_box.tag_configure("tag_key", foreground=THEME["accent"], font=("Microsoft YaHei UI", 9, "bold"))
        self.preview_box.tag_configure("tag_warn", foreground=THEME["warn"], font=("Microsoft YaHei UI", 9, "bold"))
        self.preview_box.tag_configure("tag_err", foreground=THEME["danger"], font=("Microsoft YaHei UI", 9, "bold"))
        self.preview_box.tag_configure("tag_muted", foreground=THEME["muted"])

        self.note.trace_add("write", lambda *_: self.update_draft_hint())

    def _build_history_tab(self):
        top_info = ttk.Frame(self.hist)
        top_info.pack(fill="x", pady=(0, 6))
        ttk.Label(top_info, textvariable=self.history_title, font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w")
        ttk.Label(
            top_info,
            text="按住 Ctrl 选中两轮，再点「比较两轮」。双击记录可打开原始 FIT。",
            style="MutedBg.TLabel",
        ).pack(anchor="w")

        hb = ttk.Frame(self.hist)
        hb.pack(fill="x", pady=(0, 8))
        groups = (
            [("原始 FIT", lambda: self.open_item("拟合/model.fit")),
             ("本轮 CAT", lambda: self.open_item("预测/model.cat")),
             ("本轮目录", lambda: self.open_item(""))],
            [("沿用结果 PAR", lambda: self.reuse(False)),
             ("以本轮输入为起点", lambda: self.reuse(True))],
            [("比较两轮", self.compare),
             ("复制摘要", self.copy_report),
             ("导出摘要", self.export)],
        )
        files_and_parameters = ttk.Frame(hb)
        files_and_parameters.pack(fill="x", pady=(0, 5))
        summaries = ttk.Frame(hb)
        summaries.pack(fill="x")
        for i, (row, group) in enumerate(zip((files_and_parameters, files_and_parameters, summaries), groups)):
            if i == 1:
                ttk.Separator(row, orient="vertical").pack(side="left", fill="y", padx=8, pady=2)
            for label, fn in group:
                ttk.Button(row, text=label, command=fn).pack(side="left", padx=(0, 5))

        pane = ttk.PanedWindow(self.hist, orient="vertical")
        pane.pack(fill="both", expand=True)

        # Upper pane: Runs table
        upper_card = tk.Frame(pane, bg=THEME["surface"], highlightbackground=THEME["border"], highlightthickness=1)
        upper_body = ttk.Frame(upper_card, style="Card.TFrame", padding=(10, 10, 10, 8))
        upper_body.pack(fill="both", expand=True)

        tree_wrap = ttk.Frame(upper_body, style="Card.TFrame")
        tree_wrap.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(
            tree_wrap,
            columns=("name", "lines", "rms", "state", "pub"),
            show="headings",
            selectmode="extended",
            height=8,
        )
        cols = (
            ("name", "轮次 / 备注", 380, "w", True),
            ("lines", "输入谱线", 85, "e", False),
            ("rms", "RMS / MHz", 115, "e", False),
            ("state", "状态", 75, "center", False),
            ("pub", "预测谱发布", 105, "center", False),
        )
        for cid, heading, width, anchor, stretch in cols:
            self.tree.heading(cid, text=heading, anchor=anchor)
            self.tree.column(cid, width=width, anchor=anchor, stretch=stretch)
        self.tree.tag_configure("odd", background=THEME["surface"])
        self.tree.tag_configure("even", background=THEME["zebra"])
        self.tree.tag_configure("fail", foreground=THEME["danger"], background=THEME["danger_bg"])
        self.tree.tag_configure("published", foreground=THEME["accent"])

        tree_scroll = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda _: self.show())
        self.tree.bind("<Double-1>", lambda _: self.open_default_item())

        # Lower pane: Summary metrics strip + highlighted report text
        lower_card = tk.Frame(pane, bg=THEME["surface"], highlightbackground=THEME["border"], highlightthickness=1)
        lower_body = ttk.Frame(lower_card, style="Card.TFrame", padding=10)
        lower_body.pack(fill="both", expand=True)

        metrics = ttk.Frame(lower_body, style="Card.TFrame")
        metrics.pack(fill="x", pady=(0, 8))
        metric_specs = (
            ("lines", "输入谱线"),
            ("rms", "微波 RMS"),
            ("norm", "归一化 RMS"),
            ("cat", "预测谱 CAT"),
            ("state", "本轮状态"),
        )
        for idx, (mkey, mtitle) in enumerate(metric_specs):
            box = tk.Frame(metrics, bg=THEME["surface_alt"], highlightbackground=THEME["border"], highlightthickness=1)
            box.pack(side="left", fill="x", expand=True, padx=(0 if idx == 0 else 6, 0))
            inner = ttk.Frame(box, style="Subtle.TFrame", padding=(10, 5))
            inner.pack(fill="x")
            ttk.Label(inner, text=mtitle, style="MetricKey.TLabel").pack(anchor="w")
            val_lbl = ttk.Label(inner, textvariable=self.metric_vars[mkey], style="MetricVal.TLabel")
            val_lbl.pack(anchor="w", pady=(1, 0))
            self.metric_labels[mkey] = val_lbl

        self.report = self.textbox(lower_body, readonly=True)
        self.report.configure(height=10)
        self._configure_report_tags(self.report)

        pane.add(upper_card, weight=2)
        pane.add(lower_card, weight=3)

    def textbox(self, parent, readonly=False):
        outer = tk.Frame(parent, bg=THEME["surface"], highlightbackground=THEME["border"], highlightthickness=1)
        outer.pack(fill="both", expand=True)
        t = tk.Text(
            outer,
            wrap="none",
            font=(self.mono_font, 10),
            bg=THEME["surface"],
            fg=THEME["text"],
            insertbackground=THEME["accent"],
            selectbackground=THEME["accent_soft"],
            selectforeground=THEME["text"],
            relief="flat",
            padx=10,
            pady=8,
        )
        y = ttk.Scrollbar(outer, command=t.yview)
        x = ttk.Scrollbar(outer, orient="horizontal", command=t.xview)
        outer.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        t.grid(row=0, column=0, sticky="nsew")
        y.grid(row=0, column=1, sticky="ns")
        x.grid(row=1, column=0, sticky="ew")
        t.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        if readonly:
            t.configure(state="disabled")
        return t

    def _configure_report_tags(self, t):
        t.tag_configure("heading", foreground=THEME["accent"], font=(self.mono_font, 10, "bold"))
        t.tag_configure("section", foreground=THEME["text"], font=(self.mono_font, 10, "bold"))
        t.tag_configure("sep", foreground=THEME["border_strong"])
        t.tag_configure("err", foreground=THEME["danger"], background=THEME["danger_bg"])
        t.tag_configure("warn", foreground=THEME["warn"], background=THEME["warn_bg"])
        t.tag_configure("diff_add", foreground=THEME["success"], background=THEME["success_bg"])
        t.tag_configure("diff_del", foreground=THEME["danger"], background=THEME["danger_bg"])
        t.tag_configure("diff_hunk", foreground=THEME["accent"], background=THEME["accent_soft"])

    def _set_preview(self, entries):
        self.preview_box.configure(state="normal")
        self.preview_box.delete("1.0", "end")
        if not entries:
            self.preview_box.insert("end", "先选择项目目录及所需输入文件，预检结果将显示在此处。", "tag_muted")
        else:
            for idx, (prefix, body, tag) in enumerate(entries):
                if idx:
                    self.preview_box.insert("end", "\n")
                if prefix:
                    self.preview_box.insert("end", prefix, tag or "tag_key")
                self.preview_box.insert("end", body, tag if not prefix and tag else "")
        self.preview_box.configure(state="disabled")

    def _set_metrics(self, meta=None):
        if not meta:
            for k in self.metric_vars:
                self.metric_vars[k].set("—")
                self.metric_labels[k].configure(foreground=THEME["text"])
            return
        self.metric_vars["lines"].set(f"{meta['lines']} 条" if "lines" in meta else "—")
        if meta.get("rms"):
            khz = format_rms_khz(meta["rms"])
            self.metric_vars["rms"].set(khz if khz else f"{meta['rms']} MHz")
        else:
            self.metric_vars["rms"].set("—")
        self.metric_vars["norm"].set(meta.get("norm") or "—")
        if "cat_lines" in meta:
            suffix = " · 已发布" if meta.get("published") else ""
            self.metric_vars["cat"].set(f"{meta['cat_lines']} 条{suffix}")
        else:
            self.metric_vars["cat"].set("—")
        state = meta.get("status", "—")
        self.metric_vars["state"].set(state)
        color = THEME["success"] if state == "完成" else THEME["danger"] if state == "失败" else THEME["text"]
        self.metric_labels["state"].configure(foreground=color)

    def update_draft_hint(self):
        self.draft_hint.set("● 有未运行的本轮修改或备注" if self.edits or self.note.get().strip() else "")

    def qn_count(self):
        return self.nq.get() if self.check_qn.get() else 0

    def save_pref(self, store_draft=False):
        p = self.project.get()
        self.pref["geometry"] = self.root.geometry()
        if p:
            conf = self.pref.setdefault("projects", {}).setdefault(p, {})
            conf.update(
                paths={k: v.get() for k, v in self.paths.items()},
                nq=self.qn_count(),
                qn_choice=self.nq.get(),
                mode=self.mode.get(),
                publish=self.publish.get(),
            )
            if store_draft:
                conf["draft"] = {
                    "note": self.note.get(),
                    "edits": {k: {"path": self.paths[k].get(), "hex": v.hex()} for k, v in self.edits.items()},
                }
            self.pref["last"] = p
        dump(PREFS, self.pref)

    def load_project(self, p):
        self.project.set(p)
        self.edits.clear()
        self.note.set("")
        conf = self.pref.get("projects", {}).get(p, {})
        for k, v in self.paths.items():
            v.set(conf.get("paths", {}).get(k, ""))
        self.project_name.set(f"项目：{Path(p).name}" if p else "未选择项目")
        self.result_dir.set(str(Path(p) / "运行记录") if p else "请点击右侧“切换项目…”选择工作目录")
        self.check_qn.set(bool(conf.get("nq", 0)))
        self.nq.set(conf.get("qn_choice") or conf.get("nq") or 3)
        self.mode.set(conf.get("mode", MODES[0]))
        self.fullpaths.set(False)
        draft = conf.get("draft", {})
        self.edits = {
            k: bytes.fromhex(v["hex"])
            for k, v in draft.get("edits", {}).items()
            if k in self.paths and self.paths[k].get() == v["path"]
        }
        self.note.set(draft.get("note", ""))
        self.publish.set(conf.get("publish", True))
        self.history()
        self.refresh()

    def choose_project(self):
        if self.busy:
            return
        p = filedialog.askdirectory(title="选择项目目录（将在其中保存运行记录）", initialdir=self.project.get() or None)
        if p and Path(p) != Path(self.project.get()) and self.leave_project():
            self.load_project(str(Path(p)))
            self.save_pref()

    def leave_project(self):
        if self.edits or self.note.get().strip():
            answer = messagebox.askyesnocancel("未运行的草稿", "保留本轮参数修改和备注，下次打开此项目时继续？")
            if answer is None:
                return False
            if not answer:
                self.edits.clear()
                self.note.set("")
        self.save_pref(store_draft=True)
        return True

    def close(self):
        if self.busy:
            messagebox.showinfo("运行中", "请等待当前计算完成后关闭。")
            return
        if self.leave_project():
            self.root.destroy()

    def browse(self, k):
        if self.busy:
            return
        p = filedialog.askopenfilename(
            title=LABELS[k],
            initialdir=self.project.get() or None,
            filetypes=[(LABELS[k], "*." + k), ("全部文件", "*.*")],
        )
        if p:
            self.paths[k].set(str(Path(p)))
            self.edits.pop(k, None)
            self.save_pref()
            self.refresh()

    def payload(self, k):
        return self.edits[k] if k in self.edits else Path(self.paths[k].get()).read_bytes()

    def editor(self, k):
        if self.busy:
            return
        try:
            data = self.payload(k)
            source, enc = decode(data)
        except OSError:
            messagebox.showinfo("编辑", "请先选择输入文件。")
            return
        win = tk.Toplevel(self.root)
        win.title("本轮参数设置（PAR 工作副本）" if k == "par" else "本轮预测设置（INT 工作副本）")
        win.geometry("880x560")
        win.minsize(680, 300)
        win.configure(bg=THEME["bg"])
        win.transient(self.root)
        win.grab_set()

        wrap = ttk.Frame(win, padding=12)
        wrap.pack(fill="both", expand=True)
        caption = (
            "逐行编辑 Pickett 原始输入。参数行为：代码、数值、输入约束；保留负代码关联和状态约定（不修改原文件）。"
            if k == "par"
            else "第二行依次为 FLAGS TAG QROT FBGN FEND STR0 STR1 FQLIM(GHz) TEMP(K)。其下为偶极矩代码和数值（不修改原文件）。"
        )
        caption_label = ttk.Label(wrap, text=caption, style="MutedBg.TLabel")
        caption_label.pack(fill="x", pady=(0, 8))
        caption_label.bind("<Configure>", lambda event: caption_label.configure(wraplength=event.width))
        buttons = ttk.Frame(wrap)
        buttons.pack(side="bottom", fill="x", pady=(10, 0))

        t = self.textbox(wrap)
        t.insert("1.0", source)

        def edit_field():
            raw = t.get("1.0", "end-1c").splitlines()
            try:
                if k == "par":
                    idx = int(t.index("insert").split(".")[0]) - 1
                    if idx < 3 or idx >= len(raw):
                        raise ValueError("先点击文本中要调整的参数行。")
                    head = raw[idx].split("/", 1)[0]
                    spans = list(re.finditer(r"[^\s,]+", head))
                    if len(spans) < 3:
                        raise ValueError("请选中含代码、初值和约束的参数行。")
                    int(spans[0][0])
                    field = spans[2]
                    label = f"参数 {spans[0][0]} 的输入约束（紧约束如 1E-10，宽约束如 1E10）"
                else:
                    idx = 1
                    spans = list(re.finditer(r"[^\s,]+", raw[idx].split("/", 1)[0]))
                    if len(spans) != 9 or "," in raw[idx]:
                        raise ValueError("此 INT 使用可选字段或逗号格式，请在文本区直接编辑。")
                    name = simpledialog.askstring("预测范围", "输入要调整的字段：FQLIM、FEND、TEMP", initialvalue="FQLIM", parent=win)
                    if not name:
                        return
                    name = name.strip().upper()
                    opts = {"FQLIM": (7, "频率上限（GHz）"), "FEND": (4, "角动量上限"), "TEMP": (8, "温度（K）")}
                    if name not in opts:
                        raise ValueError("字段名未识别。")
                    j, label = opts[name]
                    field = spans[j]
                value = simpledialog.askstring("调整本轮设置", label, initialvalue=field[0], parent=win)
                if value is None:
                    return
                value = value.strip()
                if not math.isfinite(pickett_float(value)):
                    raise ValueError("请输入有限数值。")
                raw[idx] = raw[idx][: field.start()] + value + raw[idx][field.end() :]
                t.delete("1.0", "end")
                t.insert("1.0", "\n".join(raw) + "\n")
                t.mark_set("insert", f"{idx + 1}.0")
                t.see("insert")
            except (ValueError, IndexError) as e:
                messagebox.showinfo("本轮设置", str(e), parent=win)

        def add_param():
            raw = t.get("1.0", "end-1c").splitlines()
            try:
                pos = int(simpledialog.askstring("参数区", "新参数应插入到第几行前？（从 1 数；末行后用末行号 + 1）", parent=win) or 0)
                if not pos:
                    return
                if not 4 <= pos <= len(raw) + 1:
                    raise ValueError("请选择有效的参数行位置。")
                entry = simpledialog.askstring("新增参数", "Pickett 参数代码  初值  约束  /注释", parent=win)
                if not entry:
                    return
                vals = re.split(r"[\s,]+", entry.split("/", 1)[0].strip())
                int(vals[0])
                if not all(math.isfinite(pickett_float(value)) for value in vals[1:3]) or len(vals) < 3:
                    raise ValueError("请输入有限的参数初值和约束。")
                raw[1], n = re.subn(r"^(\s*)(\+?\d+)", lambda m: m[1] + str(int(m[2]) + 1), raw[1], count=1)
                if not n:
                    raise ValueError("无法更新第二行参数数目，请手动编辑。")
                raw.insert(pos - 1, entry)
                t.delete("1.0", "end")
                t.insert("1.0", "\n".join(raw) + "\n")
            except (IndexError, ValueError) as e:
                messagebox.showerror("参数输入", str(e), parent=win)

        def apply():
            txt = t.get("1.0", "end-1c")
            try:
                self.edits[k] = (txt.rstrip("\r\n") + "\n").encode("utf8" if enc == "utf-8-sig" else enc)
            except UnicodeError as e:
                messagebox.showerror("编码", str(e), parent=win)
                return
            win.destroy()
            self.refresh()

        ttk.Button(buttons, text="修改所选参数约束" if k == "par" else "调整范围或温度", command=edit_field).pack(side="left")
        if k == "par":
            ttk.Button(buttons, text="新增参数并更新计数", command=add_param).pack(side="left", padx=(6, 0))
        ttk.Button(buttons, text="采用本轮编辑", style="Accent.TButton", command=apply).pack(side="right")
        ttk.Button(buttons, text="取消", command=win.destroy).pack(side="right", padx=(0, 6))

    def show_about(self):
        win = tk.Toplevel(self.root)
        win.title("关于 Pickett Runner · GitHub 资源")
        win.geometry("560x420")
        win.resizable(False, False)
        win.configure(bg=THEME["bg"])
        win.transient(self.root)
        win.grab_set()

        wrap = ttk.Frame(win, padding=14)
        wrap.pack(fill="both", expand=True)

        card, c = self._card(wrap)
        card.pack(fill="x", pady=(0, 10))
        top = ttk.Frame(c, style="Card.TFrame")
        top.pack(fill="x")
        ttk.Label(top, text="Pickett Runner", style="AppTitle.TLabel").pack(side="left")
        ttk.Label(
            c,
            text=f"微波转动光谱 SPFIT / SPCAT 迭代拟合与留痕工具\n维护者：{REPO_OWNER}   ·   零第三方依赖（Python 标准库 Tkinter）",
            style="Muted.TLabel",
            justify="left",
        ).pack(anchor="w", pady=(6, 10))

        links = ttk.Frame(c, style="Card.TFrame")
        links.pack(fill="x")
        ttk.Button(links, text="GitHub 仓库主页 ↗", style="Ghost.TButton", command=lambda: webbrowser.open(REPO_URL)).pack(side="left", padx=(0, 6))
        ttk.Button(links, text="在线使用说明 ↗", command=lambda: webbrowser.open(DOCS_URL)).pack(side="left", padx=(0, 6))
        ttk.Button(links, text="反馈问题 / Issues ↗", command=lambda: webbrowser.open(ISSUES_URL)).pack(side="left")

        info_var = tk.StringVar(value="点击下方按钮可从 GitHub 获取最新仓库动态与版本信息（断网时不影响本地解谱）。")
        latest_url = {"href": REPO_URL}

        footer = ttk.Frame(wrap)
        footer.pack(side="bottom", fill="x")

        card2, c2 = self._card(wrap, "GitHub 在线信息与版本检查")
        card2.pack(fill="both", expand=True, pady=(0, 10))
        info_box = tk.Text(
            c2,
            height=6,
            wrap="word",
            relief="flat",
            bg=THEME["surface_alt"],
            fg=THEME["text"],
            highlightbackground=THEME["border"],
            highlightthickness=1,
            padx=10,
            pady=8,
            font=("Microsoft YaHei UI", 9),
        )
        info_box.insert("1.0", info_var.get())
        info_box.configure(state="disabled")
        info_box.pack(fill="both", expand=True)

        check_btn = ttk.Button(footer, text="获取最新 GitHub 信息", style="Accent.TButton")
        check_btn.pack(side="left")
        open_new_btn = ttk.Button(footer, text="前往查看更新 ↗", command=lambda: webbrowser.open(latest_url["href"]))
        ttk.Button(footer, text="关闭", command=win.destroy).pack(side="right")

        def set_info_text(text):
            if not win.winfo_exists():
                return
            info_box.configure(state="normal")
            info_box.delete("1.0", "end")
            info_box.insert("1.0", text)
            info_box.configure(state="disabled")

        def on_check():
            check_btn.configure(state="disabled", text="正在查询 GitHub…")
            open_new_btn.pack_forget()
            set_info_text("正在连接 GitHub API 获取仓库及最新版本信息…")

            def worker():
                try:
                    data = fetch_github_info()
                    lines = [
                        f"当前版本：{VERSION} · {data['build_source']}",
                        f"仓库地址：{REPO_OWNER}/{REPO_NAME}   (★ {data['stars']} · 最近更新 {data['updated_at']})",
                    ]
                    if data.get("description"):
                        lines.append(f"仓库简介：{data['description']}")
                    if data.get("release_tag"):
                        status_txt = data["release_status"]
                        lines.append(f"最新 Release：{data['release_name']}（{data['release_date']}）— {status_txt}")
                        if data.get("release_notes"):
                            snippet = data["release_notes"][:240] + ("…" if len(data["release_notes"]) > 240 else "")
                            lines.append(f"更新说明：{snippet}")
                    elif data.get("commit_sha"):
                        lines.append(f"当前尚未发布 Release；最新提交：{data['commit_sha']}（{data['commit_date']}）")
                        if data.get("commit_msg"):
                            lines.append(f"提交说明：{data['commit_msg']}")
                    latest_url["href"] = data.get("release_url") or REPO_URL
                    msg = "\n".join(lines)
                    show_jump = bool(data.get("has_update") or data.get("release_tag"))
                except Exception as exc:
                    msg = (
                        f"当前版本：{VERSION} · {build_source()}\n"
                        f"无法获取 GitHub 信息（网络受限或超时）：{exc}\n"
                        "你可以直接点击上方按钮在浏览器中打开仓库。"
                    )
                    show_jump = False

                def finish():
                    if not win.winfo_exists():
                        return
                    set_info_text(msg)
                    check_btn.configure(state="normal", text="重新获取 GitHub 信息")
                    if show_jump:
                        open_new_btn.pack(side="left", padx=(8, 0))

                self.root.after(0, finish)

            threading.Thread(target=worker, daemon=True).start()

        check_btn.configure(command=on_check)

    def refresh(self):
        mode = MODES.index(self.mode.get())
        keys = REQUIRED[mode]
        entries = []
        self.update_draft_hint()
        self.go.configure(text=RUN_LABELS[mode])
        self.qn_hint.set(f"个（上下态合计 {2 * self.nq.get()} 项）")
        if self.check_qn.get():
            self.qn_options.pack(side="left", padx=(12, 0))
        else:
            self.qn_options.pack_forget()

        for widget, visible in (
            (self.continue_row, "par" in keys),
            (self.qn_box, "lin" in keys),
            (self.publish_row, "int" in keys),
        ):
            if visible:
                widget.grid()
            else:
                widget.grid_remove()

        for k, widgets in self.controls.items():
            for w in widgets:
                if k in keys:
                    w.grid()
                else:
                    w.grid_remove()
            if k in self.edit_buttons:
                btn = self.edit_buttons[k]
                if k in self.edits:
                    btn.configure(text="已编辑副本 ●", style="Edited.TButton")
                else:
                    btn.configure(text="编辑本轮副本", style="TButton")

            raw = self.paths[k].get()
            p = Path(raw)
            if not raw:
                self.filelabels[k].set("请选择输入文件")
                continue
            source = "项目设置" if k == "int" else "项目输入" if p.parent == Path(self.project.get()) else "指定文件"
            for folder, _ in self.items:
                if p.parent.parent == folder:
                    source = f"第 {folder.name.split('_')[0]} 轮 · {p.parent.name}"
                    break
            if not p.is_file():
                source = "文件不存在，请重新选择"
            elif k in self.edits:
                source += " · 本轮已编辑"
            self.filelabels[k].set(f"{raw if self.fullpaths.get() else p.name}  ·  {source}")

        missing = any(self.paths[k].get() and not Path(self.paths[k].get()).is_file() for k in keys)
        self.go.configure(state="disabled" if self.busy or missing else "normal")
        try:
            rows = []
            if "lin" in keys and Path(self.paths["lin"].get()).is_file():
                rows, dups, blends = records(self.payload("lin"), self.qn_count())
                last = next((m["lines"] for _, m in self.items if m.get("fit_ok")), None)
                dup_cnt = sum(c - 1 for c in dups.values())
                lin_text = (
                    f"{len(rows)} 条"
                    + (f"（最近拟合 {last} 条）" if last is not None else "")
                    + f"；完全重复 {dup_cnt} 条；同频不同量子数 {len(blends)} 组"
                )
                entries.append(("LIN  ", lin_text, "tag_warn" if dup_cnt else "tag_key"))
                previous = next((p / "输入/model.lin" for p, m in self.items if m.get("fit_ok")), None)
                if previous and previous.is_file():
                    old = Counter(" ".join(s.split()) for s in read(previous).splitlines() if s.strip())
                    new = Counter(" ".join(s.split()) for s in rows)
                    for label, change in (("加入", new - old), ("移除", old - new)):
                        if change:
                            entries.append(("     ", f"{label} {sum(change.values())} 条  示例：{next(iter(change))[:75]}", "tag_muted"))
            if "int" in keys and Path(self.paths["int"].get()).is_file():
                opt = decode(self.payload("int"))[0].splitlines()[1].split("/")[0].split()
                if len(opt) >= 9:
                    entries.append(
                        ("INT  ", f"频率上限（FQLIM）{opt[7]} GHz  ·  终止角动量（FEND）{opt[4]}  ·  温度 {opt[8]} K", "tag_key")
                    )
            if "par" in keys and Path(self.paths["par"].get()).is_file():
                opt = decode(self.payload("par"))[0].splitlines()[1].split()
                entries.append(("PAR  ", f"控制行参数数目 {opt[0]}；可在本轮副本中调整初值与约束", "tag_key"))
                if "lin" in keys and Path(self.paths["lin"].get()).is_file():
                    _, notice = ensure_line_capacity(self.payload("par"), len(rows))
                    if notice:
                        entries.append(("扩容 ", notice, "tag_warn"))
        except (ValueError, OSError, IndexError) as e:
            entries.append(("检查失败：", str(e), "tag_err"))
        if self.edits:
            entries.append(("草稿 ", "已编辑本轮副本：" + "、".join(k.upper() for k in self.edits), "tag_warn"))
        self._set_preview(entries)

    def history(self):
        self.items = runs(Path(self.project.get())) if self.project.get() else []
        self.history_title.set(
            f"当前项目：{Path(self.project.get()).name}  ·  共 {len(self.items)} 轮"
            if self.project.get()
            else "尚未选择项目"
        )
        self.tree.delete(*self.tree.get_children())
        latest_pub = next((p.name for p, m in self.items if m.get("published")), None)
        for i, (p, m) in enumerate(self.items):
            pub_mark = "★ current.cat" if p.name == latest_pub else ("已发布" if m.get("published") else "")
            tags = ["even" if i % 2 else "odd"]
            if m.get("status") == "失败":
                tags.append("fail")
            elif p.name == latest_pub:
                tags.append("published")
            self.tree.insert(
                "",
                "end",
                iid=str(i),
                values=(p.name, m.get("lines", ""), m.get("rms", ""), m["status"], pub_mark),
                tags=tuple(tags),
            )
        self._set_metrics(None)
        self.set_report("此项目尚无运行记录。" if self.project.get() and not self.items else "")
        self.status.set("最近发布 current.cat：" + latest_pub if latest_pub else "尚无本工具发布的预测谱")

    def selected(self):
        return [self.items[int(i)] for i in self.tree.selection()]

    def set_report(self, s, is_diff=False):
        self.report.configure(state="normal")
        self.report.delete("1.0", "end")
        if s:
            for idx, line in enumerate(s.splitlines(), 1):
                tag = None
                if is_diff:
                    if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
                        tag = "diff_hunk"
                    elif line.startswith("+"):
                        tag = "diff_add"
                    elif line.startswith("-"):
                        tag = "diff_del"
                    elif line.startswith(("LIN ", "PAR ", "INT ", "VAR ")):
                        tag = "section"
                    elif idx == 1:
                        tag = "heading"
                else:
                    if line.startswith("■ "):
                        tag = "heading"
                    elif line.startswith("[错误]"):
                        tag = "err"
                    elif line.startswith("[提示]"):
                        tag = "warn"
                    elif line.startswith(("逐线结果", "参数结果", "拟合警告", "预测谱 CAT", "输入来源")):
                        tag = "section"
                    elif set(line) == {"-"} and len(line) >= 20:
                        tag = "sep"
                    elif re.match(r"^\s*\d+\s+", line):
                        tail = line.split()
                        if tail:
                            try:
                                ratio = abs(float(tail[-1]))
                                if ratio >= 3.0:
                                    tag = "err"
                                elif ratio >= 2.0:
                                    tag = "warn"
                            except ValueError:
                                pass
                    elif re.search(r"warn|reject|singular|diverg|overflow", line, re.I):
                        tag = "warn"
                self.report.insert("end", line + "\n", tag or "")
        self.report.configure(state="disabled")

    def copy_report(self):
        content = self.report.get("1.0", "end-1c").strip()
        if not content:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        self.status.set("已将当前摘要复制到剪贴板")

    def export(self):
        content = self.report.get("1.0", "end-1c")
        if not content.strip():
            return
        path = filedialog.asksaveasfilename(title="导出当前结果或比较", defaultextension=".txt", filetypes=[("文本", "*.txt")])
        if path:
            try:
                atomic(Path(path), content.encode("utf-8-sig"))
            except OSError as exc:
                messagebox.showerror("导出摘要", str(exc))
                return
            self.status.set("已导出摘要：" + Path(path).name)

    def show(self):
        vals = self.selected()
        if len(vals) == 1:
            folder, meta = vals[0]
            self._set_metrics(meta)
            self.set_report(describe(folder, meta))
        else:
            self._set_metrics(None)
            self.set_report("")

    def open_default_item(self):
        vals = self.selected()
        if len(vals) != 1:
            return
        folder, _ = vals[0]
        if (folder / "拟合/model.fit").exists():
            self.open_item("拟合/model.fit")
        else:
            self.open_item("")

    def open_item(self, sub):
        vals = self.selected()
        if len(vals) != 1:
            return
        p = vals[0][0] / sub
        if not p.exists():
            messagebox.showinfo("本轮文件", "该轮没有此输出。")
            return
        if sub.endswith(".fit"):
            subprocess.Popen(["notepad.exe", str(p)])
        elif sub.endswith(".cat"):
            subprocess.Popen(["explorer.exe", "/select,", str(p)])
        else:
            os.startfile(p)

    def reuse(self, initial):
        vals = self.selected()
        if self.busy or len(vals) != 1:
            return
        folder, meta = vals[0]
        if initial:
            mode = meta.get("mode")
            if mode not in MODES:
                messagebox.showinfo("参数", "此轮的运行方式无法识别。")
                return
            paths = {k: folder / "输入" / f"model.{k}" for k in REQUIRED[MODES.index(mode)]}
            missing = [k.upper() for k, p in paths.items() if not p.is_file()]
            if missing:
                messagebox.showinfo("参数", "此轮缺少输入快照：" + "、".join(missing))
                return
            if "lin" in paths and Path(self.paths["lin"].get()).is_file() and not messagebox.askyesno(
                "线表来源", "一并选用该轮保存的 LIN 快照？选“否”将继续读取当前线表。"
            ):
                del paths["lin"]
            self.mode.set(mode)
        else:
            par = folder / "拟合/model.par"
            if not meta.get("fit_ok") or not par.is_file():
                messagebox.showinfo("参数", "此轮没有可用的参数文件。")
                return
            paths = {"par": par, "var": folder / "拟合/model.var"}
        for k, p in paths.items():
            self.paths[k].set(str(p) if p.is_file() else "")
            self.edits.pop(k, None)
        self.tabs.select(self.main)
        self.save_pref()
        self.refresh()

    def latest(self):
        if self.busy:
            return
        for i, (folder, meta) in enumerate(self.items):
            if meta.get("fit_ok") and (folder / "拟合/model.par").is_file():
                self.tree.selection_set(str(i))
                self.reuse(False)
                return
        messagebox.showinfo("参数", "尚无成功的拟合记录。")

    def compare(self):
        vals = self.selected()
        if len(vals) != 2:
            messagebox.showinfo("比较", "按住 Ctrl 选中两轮记录。")
            return
        (a, ma), (b, mb) = sorted(vals, key=lambda x: int(x[0].name.split("_")[0]))
        lines = [a.name + "  →  " + b.name, f"RMS (MHz)：{ma.get('rms', '—')}  →  {mb.get('rms', '—')}"]
        for k in ("lin", "par", "int", "var"):
            aa = a / "输入" / ("model." + k)
            bb = b / "输入" / ("model." + k)
            if aa.exists() and bb.exists():
                delta = list(
                    difflib.unified_diff(
                        read(aa).splitlines(),
                        read(bb).splitlines(),
                        fromfile=a.name,
                        tofile=b.name,
                        lineterm="",
                        n=0,
                    )
                )
                lines.extend(["", k.upper() + " 输入：" + ("有变化" if delta else "相同"), *delta])
            elif aa.is_file() or bb.is_file():
                lines.extend(["", f"{k.upper()} 输入：仅第 {(a if aa.is_file() else b).name.split('_')[0]} 轮有快照"])
        self._set_metrics(None)
        self.set_report("\n".join(lines), is_diff=True)

    def start(self):
        if self.busy:
            return
        project = self.project.get()
        if not project or not Path(project).is_dir():
            messagebox.showinfo("运行", "先选择一个项目目录。")
            return
        mode = MODES.index(self.mode.get())
        keys = REQUIRED[mode]
        nq = self.qn_count()
        try:
            paths = {k: self.paths[k].get() for k in keys}
            for k, p in paths.items():
                if not Path(p).is_file():
                    raise ValueError("请选择 " + LABELS[k])
            executable_paths(mode)
            inputs = {k: self.payload(k) for k in keys}
            if "lin" in keys:
                _, dups, _ = records(inputs["lin"], nq)
                if dups and not messagebox.askyesno(
                    "线表有完全重复记录",
                    "以下记录重复（最多列五组）：\n"
                    + "\n".join(f"{v} 次：{k}" for k, v in list(dups.items())[:5])
                    + "\n\n仍按原样运行？程序不会自动去重。",
                    default="no",
                ):
                    return
            self.save_pref()
        except (OSError, ValueError) as e:
            messagebox.showerror("检查输入", str(e))
            return

        self.submitted_note = self.note.get()
        note = self.submitted_note.strip() or self.mode.get()
        publish = self.publish.get()
        self.busy = True
        self.go.configure(state="disabled")
        self.status.set("正在运行：" + self.mode.get() + " …")

        def worker():
            try:
                self.pending.put(execute(Path(project), mode, note, paths, inputs, publish, nq))
            except Exception as e:
                self.pending.put(e)

        threading.Thread(target=worker, daemon=True).start()
        self.root.after(150, self.poll)

    def poll(self):
        try:
            result = self.pending.get_nowait()
        except queue.Empty:
            self.root.after(150, self.poll)
            return
        self.busy = False
        self.go.configure(state="normal")
        if isinstance(result, Exception):
            self.status.set("运行失败")
            messagebox.showerror("运行失败", str(result))
            return
        folder, meta = result
        if meta.get("fit_ok"):
            self.paths["par"].set(str(folder / "拟合/model.par"))
            self.edits.pop("par", None)
            self.paths["var"].set(str(folder / "拟合/model.var"))
        if meta["status"] == "完成":
            if "int" in meta["sources"]:
                self.edits.pop("int", None)
            if self.note.get() == self.submitted_note:
                self.note.set("")
        self.history()
        self.refresh()
        self.save_pref(store_draft=True)
        for i, (p, _) in enumerate(self.items):
            if p == folder:
                self.tree.selection_set(str(i))
                break
        self.tabs.select(self.hist)
        self.show()
        if meta["status"] == "失败":
            messagebox.showwarning("运行失败", meta["error"])


if __name__ == "__main__":
    enable_dpi_awareness()
    root = tk.Tk()
    icon = Path(__file__).with_name("pickett.ico")
    if icon.is_file():
        root.iconbitmap(default=str(icon))
    Window(root)
    root.mainloop()
