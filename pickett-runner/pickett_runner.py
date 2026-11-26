"""Windows desktop front end for Pickett SPFIT / SPCAT (standard library only)."""
import difflib
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import threading
import queue
from collections import Counter
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk


APP_DIR = Path(__file__).resolve().parent
BIN = APP_DIR if any((APP_DIR / name).is_file() for name in ("spfit.exe", "spcat.exe")) else APP_DIR.parent
PREFS = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "PickettRunner" / "projects.json"
MODES = ("拟合并更新预测谱", "只拟合", "只预测")
LABELS = {"lin": "实验归属 LIN", "par": "拟合模型 PAR", "int": "预测设置 INT", "var": "预测参数 VAR"}
REQUIRED = (("lin", "par", "int"), ("lin", "par"), ("var", "int"))
NUM = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][-+]?\d+)?"


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


def records(data, nq=0):
    rows = [s for s in decode(data)[0].splitlines() if s.strip()]
    if not rows:
        raise ValueError("LIN 中没有记录。")
    keys, freq = [], {}
    for n, line in enumerate(rows, 1):
        q = line[:36]
        fields = [q[i:i+3].strip() for i in range(0, 36, 3)]
        if nq and sum(bool(x) for x in fields) != 2*nq:
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
        p = subprocess.run([str(exe), "model"], cwd=cwd, stdin=subprocess.DEVNULL,
                           stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    if p.returncode:
        raise RuntimeError(f"{exe.name} 退出码 {p.returncode}。详见 {cwd.name}/运行.log")
    return read(cwd / "运行.log")


def fit_summary(report):
    rms = re.findall(r"MICROWAVE RMS\s*=\s*("+NUM+r")", report)
    norm = re.findall(r"OLD, NEW RMS ERROR=\s*"+NUM+r"\s+("+NUM+r")", report)
    block = report.rsplit("EXP.FREQ.", 1)[-1].split("NORMALIZED DIAGONAL")[0]
    residuals = []
    for line in block.splitlines():
        if not re.match(r"\s*\d+:", line):
            continue
        # The quantum-number fields are followed by decimal-valued frequencies.
        m = re.match(r"\s*(\d+):\s*(.*?)\s+([-+]?\d+\.\d+)\s+("+NUM+r")\s+("+NUM+r")\s+("+NUM+r")",line)
        if m:
            i, q, obs, calc, diff, err = m.groups()
            residuals.append((i,q.strip(),obs,calc,diff,err))
    params = report.rsplit("CHANGE THIS ITERATION",1)[-1].split("MICROWAVE AVG")[0].strip() if "CHANGE THIS ITERATION" in report else ""
    alerts = [s.strip() for s in report.splitlines() if re.search(r"warn|reject|singular|diverg|overflow",s,re.I)]
    return dict(rms=rms[-1] if rms else "", norm=norm[-1] if norm else "", residuals=residuals,
                parameters=params, alerts=list(dict.fromkeys(alerts))[-25:])


def ensure_line_capacity(data, required):
    # SPFIT writes NLINE back as the actual count. A continued fit can have more lines.
    raw=data.splitlines(keepends=True)
    if len(raw)<2:raise ValueError("PAR 缺少第二行控制参数。")
    m=re.match(rb"^\s*[+-]?\d+[ \t,]+([+-]?\d+)(?=[ \t,\r\n/]|$)",raw[1])
    if m:
        old=int(m[1])
        if 0 < abs(old) < required:
            new=required if old>0 else -required
            raw[1]=raw[1][:m.start(1)]+str(new).encode("ascii")+raw[1][m.end(1):]
            return b"".join(raw),f"本轮 LIN 有 {required} 条，工作副本 NLINE 从 {old} 扩至 {new}。"
    return data,""


def execute(project, mode, note, paths, inputs, publish, nq=0, bindir=BIN):
    folder = reserve(project / "运行记录", note)
    meta = dict(mode=MODES[mode], note=note, sources=paths, time=datetime.now().isoformat(timespec="seconds"),
                status="运行中", published=False)
    state = folder / "记录.json"
    dump(state, meta)
    snap = folder / "输入"
    try:
        snap.mkdir()
        for k, data in inputs.items():
            (snap / ("model."+k)).write_bytes(data)
        if mode != 2:
            rows, repeats, blends = records(inputs["lin"], nq)
            meta.update(lines=len(rows), repeats=repeats, same_frequency=blends)
            fit = folder / "拟合"
            fit.mkdir()
            for k in ("par","lin"):
                shutil.copyfile(snap / ("model."+k), fit / ("model."+k))
            par_data,capacity=ensure_line_capacity(inputs["par"],len(rows))
            if capacity:
                (fit/"model.par").write_bytes(par_data)
                meta["capacity"]=capacity
            log = invoke(bindir / "spfit.exe", fit)
            report = read(fit / "model.fit")
            if "FIT COMPLETE" not in (report+log).upper() or not (fit / "model.var").stat().st_size:
                raise RuntimeError("SPFIT 未确认完成。请查看本轮原始报告及日志。")
            meta.update(fit_summary(report))
            meta["fit_ok"] = True
        if mode != 1:
            pred = folder / "预测"
            pred.mkdir()
            shutil.copyfile(snap / "model.int", pred / "model.int")
            shutil.copyfile((snap if mode == 2 else fit) / "model.var", pred / "model.var")
            log = invoke(bindir / "spcat.exe", pred)
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
        try:
            result.append((f.parent, json.loads(f.read_text(encoding="utf8"))))
        except (OSError, ValueError):
            continue
    return sorted(result,key=lambda r:int(r[0].name.split("_")[0]),reverse=True)


def describe(folder, meta):
    out = [folder.name, f"{meta['mode']}　{meta['status']}　{meta['time']}"]
    if meta.get("error"):
        out.append(meta["error"])
    if meta.get("fit_ok"):
        if meta.get("capacity"):out.append(meta["capacity"])
        out += [f"输入 {meta['lines']} 条　微波 RMS {meta['rms']} MHz　归一化 RMS {meta['norm']}",
                "逐线结果（按归一化残差绝对值排序；负输入误差的红外线见原报告）",
                "序号   量子数                 实测 / MHz     计算 / MHz      残差 / kHz   误差 / kHz   残差/误差"]
        for i,q,o,c,d,e in sorted(meta["residuals"],key=lambda v:abs(float(v[4])/float(v[5])) if float(v[5]) else 0,reverse=True):
            if float(e)>0:
                out.append(f"{i:>4}   {q:<23} {o:>13} {c:>13} {1000*float(d):>12.2f} {1000*float(e):>11.2f} {float(d)/float(e):>10.2f}")
        out += ["","参数结果（数值、形式误差、本次迭代变化量）",meta["parameters"]]
        out.extend(meta.get("alerts",[]))
    if "cat_lines" in meta:
        out.append(f"CAT：{meta['cat_lines']} 条预测　" + ("已发布至 current.cat" if meta["published"] else "仅归档"))
    out += ["","输入来源（本轮实际内容见“输入”快照）"]+[f"{k.upper()}   {v}" for k,v in meta["sources"].items()]
    return "\n".join(out)


class Window:
    def __init__(self, root):
        self.root=root
        root.title("Pickett Runner | 拟合与预测")
        root.geometry("1000x735")
        root.minsize(830,620)
        try:
            self.pref=json.loads(PREFS.read_text(encoding="utf8"))
        except (OSError,ValueError):
            self.pref={}
        self.project=tk.StringVar()
        self.mode=tk.StringVar(value=MODES[0])
        self.paths={k:tk.StringVar() for k in LABELS}
        self.filelabels={k:tk.StringVar() for k in LABELS}
        self.fullpaths=tk.BooleanVar()
        self.project_title=tk.StringVar()
        self.result_dir=tk.StringVar()
        self.history_title=tk.StringVar()
        self.check_qn=tk.BooleanVar()
        self.qn_hint=tk.StringVar()
        self.draft_hint=tk.StringVar()
        self.edits={}
        self.nq=tk.IntVar(value=0)
        self.publish=tk.BooleanVar(value=True)
        self.note=tk.StringVar()
        self.status=tk.StringVar()
        self.preview=tk.StringVar()
        self.pending=queue.Queue()
        self.busy=False
        frame=ttk.Frame(root,padding=12)
        frame.pack(fill="both",expand=True)
        bar=ttk.Frame(frame);bar.pack(fill="x")
        ttk.Label(bar,textvariable=self.project_title).pack(side="left")
        ttk.Entry(bar,textvariable=self.result_dir,state="readonly").pack(side="left",fill="x",expand=True,padx=8)
        ttk.Button(bar,text="切换项目…",command=self.choose_project).pack(side="right")
        tabs=self.tabs=ttk.Notebook(frame);tabs.pack(fill="both",expand=True,pady=10)
        run=self.main=ttk.Frame(tabs,padding=12)
        hist=self.hist=ttk.Frame(tabs,padding=8)
        tabs.add(run,text="运行与输入");tabs.add(hist,text="记录与结果")
        run.columnconfigure(1,weight=1)
        ttk.Label(run,text="运行方式").grid(row=0,column=0,sticky="w")
        switches=ttk.Frame(run);switches.grid(row=0,column=1,columnspan=3,sticky="w")
        for label in MODES:
            ttk.Radiobutton(switches,text=label,variable=self.mode,value=label,command=self.refresh).pack(side="left",padx=(0,12))
        ttk.Checkbutton(switches,text="显示完整路径",variable=self.fullpaths,command=self.refresh).pack(side="left")
        self.controls={}
        for i,(k,label) in enumerate(LABELS.items(),1):
            title=ttk.Label(run,text=label);title.grid(row=i,column=0,sticky="w",pady=8)
            entry=ttk.Entry(run,textvariable=self.filelabels[k],state="readonly");entry.grid(row=i,column=1,sticky="ew",padx=8)
            browse=ttk.Button(run,text="浏览…",command=lambda k=k:self.browse(k));browse.grid(row=i,column=2)
            edit=None
            if k in ("par","int"):
                edit=ttk.Button(run,text="编辑本轮副本",command=lambda k=k:self.editor(k));edit.grid(row=i,column=3,padx=4)
            self.controls[k]=[w for w in (title,entry,browse,edit) if w is not None]
        self.continue_button=ttk.Button(run,text="沿用最近成功拟合的参数",command=self.latest)
        self.continue_button.grid(row=5,column=1,sticky="w",padx=8)
        ttk.Separator(run).grid(row=6,column=0,columnspan=4,sticky="ew",pady=15)
        ttk.Label(run,text="本轮备注").grid(row=7,column=0,sticky="w")
        ttk.Entry(run,textvariable=self.note).grid(row=7,column=1,columnspan=3,sticky="ew",padx=8)
        self.qn_box=line=ttk.Frame(run);line.grid(row=8,column=0,columnspan=4,sticky="w",pady=8)
        ttk.Checkbutton(line,text="检查每条跃迁的量子数个数",variable=self.check_qn,command=self.refresh).pack(side="left")
        self.qn_options=opts=ttk.Frame(line);opts.pack(side="left",padx=8)
        ttk.Label(opts,text="每个能级").pack(side="left")
        ttk.Spinbox(opts,from_=1,to=6,width=3,textvariable=self.nq,state="readonly",command=self.refresh).pack(side="left")
        ttk.Label(opts,textvariable=self.qn_hint).pack(side="left")
        ttk.Button(line,text="怎么选？",command=lambda:messagebox.showinfo("量子数个数",
            "按一个能级实际使用的标签计数。例如 J、Ka、Kc 共 3 项；再加内部态标签 v，就是 4 项。超精细结构按实际耦合标签计数。\n此项只核对每行填写的总数。重复记录始终单独检查。")).pack(side="right")
        self.publish_button=ttk.Checkbutton(run,text="预测成功后更新项目中的 current.cat",variable=self.publish)
        self.publish_button.grid(row=9,column=1,columnspan=3,sticky="w")
        ttk.Label(run,textvariable=self.preview,wraplength=815,justify="left").grid(row=10,column=0,columnspan=4,sticky="w",pady=12)
        actions=ttk.Frame(run);actions.grid(row=11,column=0,columnspan=4,sticky="ew")
        ttk.Button(actions,text="重新检查输入",command=self.refresh).pack(side="left")
        self.go=ttk.Button(actions,text="运行",command=self.start);self.go.pack(side="right")
        ttk.Label(actions,textvariable=self.draft_hint).pack(side="left",padx=8)
        self.note.trace_add("write",lambda *_:self.update_draft_hint())
        ttk.Label(hist,textvariable=self.history_title).pack(anchor="w",pady=(0,5))
        self.tree=ttk.Treeview(hist,columns=("name","lines","rms","state"),show="headings",selectmode="extended",height=7)
        for c,t,w in zip(self.tree["columns"],("轮次 / 备注","输入记录","RMS / MHz","状态"),(400,85,110,80)):
            self.tree.heading(c,text=t);self.tree.column(c,width=w,stretch=c=="name")
        self.tree.pack(fill="x");self.tree.bind("<<TreeviewSelect>>",lambda _:self.show())
        hb=ttk.Frame(hist);hb.pack(fill="x",pady=6)
        for label,fn in [("原始 FIT",lambda:self.open_item("拟合/model.fit")),("本轮 CAT",lambda:self.open_item("预测/model.cat")),
                         ("本轮目录",lambda:self.open_item("")),("沿用结果 PAR",lambda:self.reuse(False)),
                         ("以本轮输入为起点",lambda:self.reuse(True)),("比较两轮",self.compare),("导出摘要",self.export)]:
            ttk.Button(hb,text=label,command=fn).pack(side="left",padx=2)
        self.report=self.textbox(hist)
        ttk.Label(frame,textvariable=self.status,wraplength=920).pack(anchor="w")
        self.load_project(self.pref.get("last",""))
        root.protocol("WM_DELETE_WINDOW",self.close)

    @staticmethod
    def textbox(parent):
        f=ttk.Frame(parent);f.pack(fill="both",expand=True)
        t=tk.Text(f,wrap="none",font=("Consolas",10))
        y=ttk.Scrollbar(f,command=t.yview);x=ttk.Scrollbar(f,orient="horizontal",command=t.xview)
        f.rowconfigure(0,weight=1);f.columnconfigure(0,weight=1)
        t.grid(row=0,column=0,sticky="nsew");y.grid(row=0,column=1,sticky="ns");x.grid(row=1,column=0,sticky="ew")
        t.configure(yscrollcommand=y.set,xscrollcommand=x.set)
        return t

    def update_draft_hint(self):
        self.draft_hint.set("有未运行的本轮修改" if self.edits or self.note.get().strip() else "")

    def qn_count(self):
        return self.nq.get() if self.check_qn.get() else 0

    def save_pref(self,store_draft=False):
        p=self.project.get()
        if p:
            conf=self.pref.setdefault("projects",{}).setdefault(p,{})
            conf.update(paths={k:v.get() for k,v in self.paths.items()},nq=self.qn_count(),qn_choice=self.nq.get(),
                mode=self.mode.get(),publish=self.publish.get())
            if store_draft:
                conf["draft"]={"note":self.note.get(),"edits":{k:{"path":self.paths[k].get(),"hex":v.hex()} for k,v in self.edits.items()}}
            self.pref["last"]=p
            dump(PREFS,self.pref)

    def load_project(self,p):
        self.project.set(p);self.edits.clear();self.note.set("")
        conf=self.pref.get("projects",{}).get(p,{})
        for k,v in self.paths.items():
            v.set(conf.get("paths",{}).get(k,""))
        self.project_title.set("项目："+Path(p).name+"　结果目录" if p else "未选择项目")
        self.result_dir.set(str(Path(p)/"运行记录") if p else "")
        self.check_qn.set(bool(conf.get("nq",0)))
        self.nq.set(conf.get("qn_choice") or conf.get("nq") or 3);self.mode.set(conf.get("mode",MODES[0]))
        self.fullpaths.set(False)
        draft=conf.get("draft",{})
        self.edits={k:bytes.fromhex(v["hex"]) for k,v in draft.get("edits",{}).items() if k in self.paths and self.paths[k].get()==v["path"]}
        self.note.set(draft.get("note",""))
        self.publish.set(conf.get("publish",True))
        self.history();self.refresh()

    def choose_project(self):
        if self.busy:return
        p=filedialog.askdirectory(title="选择项目目录（将在其中保存运行记录）",initialdir=self.project.get() or None)
        if p and Path(p)!=Path(self.project.get()) and self.leave_project():
            self.load_project(str(Path(p)));self.save_pref()

    def leave_project(self):
        if self.edits or self.note.get().strip():
            answer=messagebox.askyesnocancel("未运行的草稿","保留本轮参数修改和备注，下次打开此项目时继续？")
            if answer is None:return False
            if not answer:
                self.edits.clear();self.note.set("")
        self.save_pref(store_draft=True)
        return True

    def close(self):
        if self.busy:
            messagebox.showinfo("运行中","请等待当前计算完成后关闭。");return
        if self.leave_project():self.root.destroy()

    def browse(self,k):
        if self.busy:return
        p=filedialog.askopenfilename(title=LABELS[k],initialdir=self.project.get() or None,
            filetypes=[(LABELS[k],"*."+k),("全部文件","*.*")])
        if p:
            self.paths[k].set(str(Path(p)));self.edits.pop(k,None);self.save_pref();self.refresh()

    def payload(self,k):
        return self.edits[k] if k in self.edits else Path(self.paths[k].get()).read_bytes()

    def editor(self,k):
        if self.busy:return
        try:
            data=self.payload(k);source,enc=decode(data)
        except OSError:
            messagebox.showinfo("编辑","请先选择输入文件。");return
        win=tk.Toplevel(self.root);win.title("本轮参数设置" if k=="par" else "本轮预测设置");win.geometry("850x530")
        win.transient(self.root);win.grab_set()
        caption=("逐行编辑 Pickett 原始输入。参数行为 代码、数值、输入约束；保留负代码关联和状态约定。"
                 if k=="par" else "第二行依次为 FLAGS TAG QROT FBGN FEND STR0 STR1 FQLIM(GHz) TEMP(K)。其下为偶极矩代码和数值。")
        ttk.Label(win,text=caption,wraplength=780,padding=8).pack(anchor="w")
        buttons=ttk.Frame(win);buttons.pack(side="bottom",fill="x",pady=6)
        t=self.textbox(win);t.insert("1.0",source)
        def edit_field():
            raw=t.get("1.0","end-1c").splitlines()
            try:
                if k=="par":
                    idx=int(t.index("insert").split(".")[0])-1
                    if idx<3 or idx>=len(raw):raise ValueError("先点击文本中要调整的参数行。")
                    head=raw[idx].split("/",1)[0]
                    spans=list(re.finditer(r"[^\s,]+",head))
                    if len(spans)<3:raise ValueError("请选中含代码、初值和约束的参数行。")
                    int(spans[0][0])
                    field=spans[2]
                    label=f"参数 {spans[0][0]} 的输入约束（紧约束如 1E-10，宽约束如 1E10）"
                else:
                    idx=1
                    spans=list(re.finditer(r"[^\s,]+",raw[idx].split("/",1)[0]))
                    if len(spans)!=9 or "," in raw[idx]:raise ValueError("此 INT 使用可选字段或逗号格式，请在文本区直接编辑。")
                    name=simpledialog.askstring("预测范围","输入要调整的字段：FQLIM、FEND、TEMP",initialvalue="FQLIM",parent=win)
                    if not name:return
                    name=name.strip().upper()
                    opts={"FQLIM":(7,"频率上限（GHz）"),"FEND":(4,"角动量上限"),"TEMP":(8,"温度（K）")}
                    if name not in opts:raise ValueError("字段名未识别。")
                    j,label=opts[name];field=spans[j]
                value=simpledialog.askstring("调整本轮设置",label,initialvalue=field[0],parent=win)
                if value is None:return
                value=value.strip()
                if not math.isfinite(float(value.replace("D","E").replace("d","e"))):raise ValueError("请输入有限数值。")
                raw[idx]=raw[idx][:field.start()]+value+raw[idx][field.end():]
                t.delete("1.0","end");t.insert("1.0","\n".join(raw)+"\n")
                t.mark_set("insert",f"{idx+1}.0");t.see("insert")
            except (ValueError,IndexError) as e:messagebox.showinfo("本轮设置",str(e),parent=win)
        def add_param():
            raw=t.get("1.0","end-1c").splitlines()
            try:
                pos=int(simpledialog.askstring("参数区","新参数应插入到第几行前？（从 1 数；末行后用末行号 + 1）",parent=win) or 0)
                if not pos:return
                if not 4<=pos<=len(raw)+1:raise ValueError("请选择有效的参数行位置。")
                entry=simpledialog.askstring("新增参数","Pickett 参数代码  初值  约束  /注释",parent=win)
                if not entry:return
                vals=entry.split("/")[0].split();int(vals[0]);float(vals[1]);float(vals[2])
                raw[1],n=re.subn(r"^(\s*)(\d+)",lambda m:m[1]+str(int(m[2])+1),raw[1],count=1)
                if not n:raise ValueError("无法更新第二行参数数目，请手动编辑。")
                raw.insert(pos-1,entry);t.delete("1.0","end");t.insert("1.0","\n".join(raw)+"\n")
            except (IndexError,ValueError) as e:messagebox.showerror("参数输入",str(e),parent=win)
        def apply():
            txt=t.get("1.0","end-1c")
            try:
                self.edits[k]=(txt.rstrip("\r\n")+"\n").encode("utf8" if enc=="utf-8-sig" else enc)
            except UnicodeError as e:messagebox.showerror("编码",str(e),parent=win);return
            win.destroy();self.refresh()
        ttk.Button(buttons,text="修改所选参数约束" if k=="par" else "调整范围或温度",command=edit_field).pack(side="left")
        if k=="par":ttk.Button(buttons,text="新增参数并更新计数",command=add_param).pack(side="left")
        ttk.Button(buttons,text="采用本轮编辑",command=apply).pack(side="right")
        ttk.Button(buttons,text="取消",command=win.destroy).pack(side="right")

    def refresh(self):
        mode=MODES.index(self.mode.get());keys=REQUIRED[mode];lines=[]
        self.update_draft_hint()
        self.qn_hint.set(f" 个，上下态合计 {2*self.nq.get()} 项")
        if self.check_qn.get():self.qn_options.pack(side="left",padx=8)
        else:self.qn_options.pack_forget()
        for widget,visible in ((self.continue_button,"par" in keys),(self.qn_box,"lin" in keys),(self.publish_button,"int" in keys)):
            if visible:widget.grid()
            else:widget.grid_remove()
        for k,widgets in self.controls.items():
            for w in widgets:
                if k in keys:w.grid()
                else:w.grid_remove()
            raw=self.paths[k].get();p=Path(raw)
            if not raw:
                self.filelabels[k].set("请选择输入文件");continue
            source="项目设置" if k=="int" else "项目输入" if p.parent==Path(self.project.get()) else "指定文件"
            for folder,m in self.items:
                if p.parent.parent==folder:
                    source=f"第 {folder.name.split('_')[0]} 轮 · {p.parent.name}";break
            if not p.is_file():source="文件不存在，请重新选择"
            elif k in self.edits:source+=" · 本轮已编辑"
            self.filelabels[k].set(f"{raw if self.fullpaths.get() else p.name}　·　{source}")
        missing=any(self.paths[k].get() and not Path(self.paths[k].get()).is_file() for k in keys)
        self.go.configure(state="disabled" if self.busy or missing else "normal")
        try:
            if "lin" in keys and Path(self.paths["lin"].get()).is_file():
                rows,dups,blends=records(self.payload("lin"),self.qn_count())
                last=next((m['lines'] for _,m in self.items if m.get("fit_ok")),None)
                lines.append(f"LIN：{len(rows)} 条"+(f"（最近拟合 {last} 条）" if last is not None else "")+
                             f"；完全重复 {sum(c-1 for c in dups.values())} 条；同频不同量子数 {len(blends)} 组")
                previous=next((p/"输入/model.lin" for p,m in self.items if m.get("fit_ok")),None)
                if previous and previous.is_file():
                    old=Counter(" ".join(s.split()) for s in read(previous).splitlines() if s.strip())
                    new=Counter(" ".join(s.split()) for s in rows)
                    for label,change in (("加入",new-old),("移除",old-new)):
                        if change:
                            lines.append(f"{label} {sum(change.values())} 条　示例："+next(iter(change))[:75])
            if "int" in keys and Path(self.paths["int"].get()).is_file():
                opt=decode(self.payload("int"))[0].splitlines()[1].split("/")[0].split()
                if len(opt)>=9:lines.append(f"INT：频率上限（FQLIM）{opt[7]} GHz　终止角动量量子数（FEND）{opt[4]}　温度 {opt[8]} K")
            if "par" in keys and Path(self.paths["par"].get()).is_file():
                opt=decode(self.payload("par"))[0].splitlines()[1].split()
                lines.append(f"PAR：控制行参数数目 {opt[0]}；可在本轮副本中调整初值与约束")
                if "lin" in keys and Path(self.paths["lin"].get()).is_file():
                    _,notice=ensure_line_capacity(self.payload("par"),len(rows))
                    if notice:lines.append(notice)
        except (ValueError,OSError,IndexError) as e:lines.append(str(e))
        if self.edits:lines.append("已编辑本轮副本："+"、".join(k.upper() for k in self.edits))
        self.preview.set("\n".join(lines) or "先选择项目及所需输入文件。")

    def history(self):
        self.items=runs(Path(self.project.get())) if self.project.get() else []
        self.history_title.set(f"当前项目：{Path(self.project.get()).name}　·　共 {len(self.items)} 轮" if self.project.get() else "尚未选择项目")
        self.tree.delete(*self.tree.get_children())
        for i,(p,m) in enumerate(self.items):
            self.tree.insert("","end",iid=str(i),values=(p.name,m.get("lines",""),m.get("rms",""),m["status"]))
        self.set_report("此项目尚无运行记录。" if self.project.get() and not self.items else "")
        published=next((p.name for p,m in self.items if m.get("published")),None)
        self.status.set("最近发布 current.cat："+published if published else "尚无本工具发布的预测谱")

    def selected(self):
        return [self.items[int(i)] for i in self.tree.selection()]

    def set_report(self,s):
        self.report.configure(state="normal");self.report.delete("1.0","end");self.report.insert("1.0",s);self.report.configure(state="disabled")

    def export(self):
        content=self.report.get("1.0","end-1c")
        if not content:return
        path=filedialog.asksaveasfilename(title="导出当前结果或比较",defaultextension=".txt",filetypes=[("文本","*.txt")])
        if path:atomic(Path(path),content.encode("utf-8-sig"))

    def show(self):
        vals=self.selected()
        if len(vals)==1:self.set_report(describe(*vals[0]))

    def open_item(self,sub):
        vals=self.selected()
        if len(vals)!=1:return
        p=vals[0][0]/sub
        if not p.exists():messagebox.showinfo("本轮文件","该轮没有此输出。");return
        if sub.endswith(".fit"):subprocess.Popen(["notepad.exe",str(p)])
        elif sub.endswith(".cat"):subprocess.Popen(["explorer.exe","/select,",str(p)])
        else:os.startfile(p)

    def reuse(self,initial):
        vals=self.selected()
        if self.busy or len(vals)!=1:return
        folder,m=vals[0];p=folder/("输入" if initial else "拟合")/"model.par"
        if not p.is_file() or (not initial and not m.get("fit_ok")):
            messagebox.showinfo("参数","此轮没有可用的参数文件。");return
        self.paths["par"].set(str(p));self.edits.pop("par",None)
        if initial and (folder/"输入/model.lin").exists():
            if messagebox.askyesno("线表来源","一并选用该轮保存的 LIN 快照？选“否”将继续读取当前线表。"):
                self.paths["lin"].set(str(folder/"输入/model.lin"))
        self.tabs.select(self.main);self.save_pref();self.refresh()

    def latest(self):
        if self.busy:return
        for i,(p,m) in enumerate(self.items):
            if m.get("fit_ok"):
                self.tree.selection_set(str(i));self.reuse(False);return
        messagebox.showinfo("参数","尚无成功的拟合记录。")

    def compare(self):
        vals=self.selected()
        if len(vals)!=2:messagebox.showinfo("比较","按住 Ctrl 选中两轮记录。");return
        (a,ma),(b,mb)=sorted(vals,key=lambda x:int(x[0].name.split("_")[0]))
        lines=[a.name+" → "+b.name,f"RMS (MHz)：{ma.get('rms','—')} → {mb.get('rms','—')}"]
        for k in ("lin","par","int","var"):
            aa=a/"输入"/("model."+k);bb=b/"输入"/("model."+k)
            if aa.exists() and bb.exists():
                delta=list(difflib.unified_diff(read(aa).splitlines(),read(bb).splitlines(),fromfile=a.name,tofile=b.name,lineterm="",n=0))
                lines.extend(["",k.upper()+" 输入："+("有变化" if delta else "相同"),*delta])
        self.set_report("\n".join(lines))

    def start(self):
        if self.busy:return
        project=self.project.get()
        if not project or not Path(project).is_dir():
            messagebox.showinfo("运行","先选择一个项目目录。");return
        mode=MODES.index(self.mode.get());keys=REQUIRED[mode];nq=self.qn_count()
        try:
            paths={k:self.paths[k].get() for k in keys}
            for k,p in paths.items():
                if not Path(p).is_file():raise ValueError("请选择 "+LABELS[k])
            executables = ("spfit.exe", "spcat.exe") if mode == 0 else ("spfit.exe",) if mode == 1 else ("spcat.exe",)
            missing = [name for name in executables if not (BIN / name).is_file()]
            if missing:
                raise ValueError("缺少 " + "、".join(missing) + "。请将相应程序放在 Pickett Runner 脚本所在目录，或其上一级目录。")
            inputs={k:self.payload(k) for k in keys}
            if "lin" in keys:
                _,dups,_=records(inputs["lin"],nq)
                if dups and not messagebox.askyesno("线表有完全重复记录",
                    "以下记录重复（最多列五组）：\n"+"\n".join(f"{v} 次：{k}" for k,v in list(dups.items())[:5])+
                    "\n\n仍按原样运行？程序不会自动去重。",default="no"):return
            self.save_pref()
        except (OSError,ValueError) as e:messagebox.showerror("检查输入",str(e));return
        self.submitted_note=self.note.get()
        note=self.submitted_note.strip() or self.mode.get();publish=self.publish.get()
        self.busy=True;self.go.configure(state="disabled");self.status.set("正在运行 "+self.mode.get())
        def worker():
            try:self.pending.put(execute(Path(project),mode,note,paths,inputs,publish,nq))
            except Exception as e:self.pending.put(e)
        threading.Thread(target=worker,daemon=True).start()
        self.root.after(150,self.poll)

    def poll(self):
        try:result=self.pending.get_nowait()
        except queue.Empty:self.root.after(150,self.poll);return
        self.busy=False;self.go.configure(state="normal")
        if isinstance(result,Exception):
            self.status.set("运行失败");messagebox.showerror("运行失败",str(result));return
        folder,meta=result
        if meta.get("fit_ok"):
            self.paths["par"].set(str(folder/"拟合/model.par"));self.edits.pop("par",None)
            self.paths["var"].set(str(folder/"拟合/model.var"))
        if meta["status"]=="完成":
            if "int" in meta["sources"]:self.edits.pop("int",None)
            if self.note.get()==self.submitted_note:self.note.set("")
        self.history();self.refresh();self.save_pref(store_draft=True)
        for i,(p,m) in enumerate(self.items):
            if p==folder:self.tree.selection_set(str(i));break
        self.tabs.select(self.hist);self.show()
        if meta["status"]=="失败":messagebox.showwarning("运行失败",meta["error"])


if __name__=="__main__":
    root=tk.Tk()
    icon=Path(__file__).with_name("pickett.ico")
    if icon.is_file():
        root.iconbitmap(default=str(icon))
    Window(root)
    root.mainloop()
