"""デバッグモードで出す、CPU・メモリ・GPU・VRAM の使用率を取る。

描く処理を遅くしないよう、画面の糸では呼ばず、裏の糸から 1〜2 秒ごとに 1 回だけ呼ぶ（atelier/ui/usage_meter.py）。
取れない部品（psutil、nvidia-ml-py、torch）や GPU の無い機械では、値の代わりに理由を返し、落とさない。
torch は自分では読み込まない（読み込むだけで数秒と数百 MB かかる）。描く処理が既に読んでいるときだけ使う。
"""
from __future__ import annotations

import os
import sys
import time

GB = 1024 ** 3


def _psutil():
    try:
        import psutil
        return psutil
    except Exception:   # 配る版に入っていない、壊れている
        return None


class _Nvml:
    """pynvml（nvidia-ml-py）を 1 回だけ初期化して使い回す。初期化に失敗した理由も覚える"""
    def __init__(self):
        self.ready = False
        self.why = ""
        self.mod = None

    def start(self):
        if self.ready or self.why:
            return self.ready
        try:
            import pynvml
        except Exception:
            self.why = "nvidia-ml-py が入っていません"
            return False
        try:
            pynvml.nvmlInit()
        except Exception as e:
            name = type(e).__name__
            self.why = ("NVIDIA の GPU とドライバーが見つかりません" if "NotFound" in name or "DriverNotLoaded" in name
                        else f"NVIDIA の GPU を読めません（{name}）")
            return False
        self.mod, self.ready = pynvml, True
        return True


_nvml = _Nvml()


def _gpu_nvml(pids: set[int]) -> dict | None:
    if not _nvml.start():
        return None
    n = _nvml.mod
    try:
        h = n.nvmlDeviceGetHandleByIndex(0)
        util = n.nvmlDeviceGetUtilizationRates(h).gpu
        mem = n.nvmlDeviceGetMemoryInfo(h)
        name = n.nvmlDeviceGetName(h)
        name = name.decode() if isinstance(name, bytes) else str(name)
        mine = 0
        try:
            for p in n.nvmlDeviceGetComputeRunningProcesses(h):
                if p.pid in pids and p.usedGpuMemory:
                    mine += p.usedGpuMemory
        except Exception:
            mine = None   # Windows の WDDM では処理ごとの量が取れないことがある
        return {"name": name, "util": float(util), "used": mem.used / GB, "total": mem.total / GB,
                "mine": (mine / GB) if mine is not None else None, "source": "nvidia-ml-py"}
    except Exception as e:
        _nvml.why = f"GPU の値を読めませんでした（{type(e).__name__}）"
        _nvml.ready = False
        return None


def _gpu_torch() -> dict | None:
    torch = sys.modules.get("torch")
    if torch is None:
        return None
    try:
        if not torch.cuda.is_available():
            return None
        free, total = torch.cuda.mem_get_info()
        return {"allocated": torch.cuda.memory_allocated() / GB, "reserved": torch.cuda.memory_reserved() / GB,
                "free": free / GB, "total": total / GB}
    except Exception:
        return None


def sample(stage: str = "") -> dict:
    """1 回分の値。取れなかった物は None にし、理由を why に入れる。took は取るのにかかった秒"""
    t0 = time.perf_counter()
    out = {"cpu": None, "cpu_mine": None, "mem_used": None, "mem_total": None, "mem_pct": None,
           "mem_mine": None, "procs": [], "gpu": None, "torch": None, "why": {}, "stage": stage}
    ps = _psutil()
    pids = {os.getpid()}
    if ps is None:
        out["why"]["cpu"] = out["why"]["mem"] = "psutil が入っていません"
    else:
        try:
            out["cpu"] = ps.cpu_percent(None)   # 前の呼び出しからの平均。初回は 0
            vm = ps.virtual_memory()
            out["mem_used"], out["mem_total"], out["mem_pct"] = (vm.total - vm.available) / GB, vm.total / GB, vm.percent
            me = ps.Process()
            procs = [me]
            try:
                procs += me.children(recursive=True)
            except Exception:
                pass
            cpu_mine = mem_mine = 0.0
            ncpu = ps.cpu_count() or 1
            for p in procs:
                try:
                    with p.oneshot():
                        c = _proc_cpu(p) / ncpu
                        r = p.memory_info().rss / GB
                        out["procs"].append({"pid": p.pid, "name": p.name(), "cpu": c, "mem": r})
                    pids.add(p.pid)
                    cpu_mine += c
                    mem_mine += r
                except Exception:
                    continue
            out["cpu_mine"], out["mem_mine"] = cpu_mine, mem_mine
        except Exception as e:
            out["why"]["cpu"] = out["why"]["mem"] = f"読めませんでした（{type(e).__name__}）"
    out["gpu"] = _gpu_nvml(pids)
    out["torch"] = _gpu_torch()
    if out["gpu"] is None:
        out["why"]["gpu"] = _nvml.why or "GPU が見つかりません"
    out["took"] = time.perf_counter() - t0
    return out


_PROC = {}


def _proc_cpu(p) -> float:
    """処理ごとの CPU。psutil.Process を覚えておかないと毎回 0 になるので、pid ごとに持つ"""
    keep = _PROC.get(p.pid)
    if keep is None:
        _PROC[p.pid] = p
        p.cpu_percent(None)   # 初回は基準を取るだけ
        return 0.0
    return keep.cpu_percent(None)


def _gb(x):
    return f"{x:.1f}"


def line(s: dict) -> str:
    """帯の右端に出す短い 1 行"""
    parts = []
    if s.get("stage"):
        parts.append(s["stage"])
    parts.append(f"CPU {s['cpu']:.0f}%" if s.get("cpu") is not None else "CPU 取得できません")
    if s.get("mem_used") is not None:
        parts.append(f"メモリ {_gb(s['mem_used'])}/{s['mem_total']:.0f} GB")
    else:
        parts.append("メモリ 取得できません")
    g = s.get("gpu")
    t = s.get("torch")
    if g:
        parts.append(f"GPU {g['util']:.0f}%")
        parts.append(f"VRAM {_gb(g['used'])}/{g['total']:.0f} GB")
    elif t:
        parts.append(f"VRAM {_gb(t['total'] - t['free'])}/{t['total']:.0f} GB")
    else:
        parts.append("GPU 取得できません")
    return " | ".join(parts)


def tip(s: dict) -> str:
    """帯の 1 行に合わせるツールチップ。取れなかった物は理由を書く"""
    rows = []
    if s.get("cpu_mine") is not None:
        rows.append(f"AtelIer の CPU {s['cpu_mine']:.0f}%、メモリ {_gb(s['mem_mine'])} GB")
    for k, label in (("cpu", "CPU とメモリ"), ("gpu", "GPU")):
        if k in s.get("why", {}) and not (k == "gpu" and s.get("torch")):
            rows.append(f"{label} 取得できません: {s['why'][k]}")
    rows.append("押すと細かい表を出します")
    return "\n".join(dict.fromkeys(rows))


def table(s: dict) -> list[tuple[str, str]]:
    """細かい表の行（項目, 値）"""
    def v(x, fmt):
        return fmt.format(x) if x is not None else "取得できません"
    rows = [("CPU（全体）", v(s.get("cpu"), "{:.0f}%")), ("CPU（AtelIer）", v(s.get("cpu_mine"), "{:.0f}%")),
            ("メモリ（全体）", f"{_gb(s['mem_used'])} / {_gb(s['mem_total'])} GB（{s['mem_pct']:.0f}%）"
             if s.get("mem_used") is not None else "取得できません"),
            ("メモリ（AtelIer）", f"{_gb(s['mem_mine'])} GB（{100 * s['mem_mine'] / s['mem_total']:.1f}%）"
             if s.get("mem_mine") is not None and s.get("mem_total") else "取得できません")]
    for p in s.get("procs", []):
        rows.append((f"  {p['name']}（{p['pid']}）", f"CPU {p['cpu']:.0f}%、メモリ {_gb(p['mem'])} GB"))
    g, t = s.get("gpu"), s.get("torch")
    if g:
        rows += [("GPU", g["name"]), ("GPU の使用率", f"{g['util']:.0f}%"),
                 ("VRAM（全体）", f"{_gb(g['used'])} / {_gb(g['total'])} GB"),
                 ("VRAM（AtelIer）", f"{_gb(g['mine'])} GB" if g.get("mine") is not None else "取得できません")]
    else:
        rows.append(("GPU", "取得できません: " + s.get("why", {}).get("gpu", "")))
    if t:
        rows += [("模型が使っている VRAM", f"{_gb(t['allocated'])} GB（確保 {_gb(t['reserved'])} GB）"),
                 ("VRAM の空き（torch）", f"{_gb(t['free'])} / {_gb(t['total'])} GB")]
    if s.get("stage"):
        rows.append(("今の工程", s["stage"]))
    rows.append(("取得にかかった時間", f"{1000 * s.get('took', 0):.1f} ミリ秒"))
    return rows
