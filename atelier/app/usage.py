"""デバッグモードで出す使用率（CPU・メモリ）。

デバッグのとき、いつもタスクマネージャーを開いて使用率を見ていた
利用者のための物。標準ライブラリだけで測る（外部の部品は足さない）。
GPU の使用率は標準ライブラリでは取れないので、出さない。
"""
import os
import time


class CpuMeter:
    """アプリの CPU 使用率。前回との差分で測るので、初回は None。

    物差しはタスクマネージャーと同じ（全コア合計を 100% とする）。
    """

    def __init__(self):
        self._last = None

    def sample(self, wall=None, proc=None):
        wall = time.monotonic() if wall is None else wall
        if proc is None:
            t = os.times()
            proc = t.user + t.system
        last, self._last = self._last, (wall, proc)
        if last is None or wall <= last[0]:
            return None
        pct = (proc - last[1]) / (wall - last[0]) / (os.cpu_count() or 1) * 100
        return max(0.0, min(100.0, pct))


def proc_mb() -> float:
    """このアプリ自身のメモリ（MB）。分からなければ 0"""
    try:
        if os.name == "nt":
            import ctypes

            class Counters(ctypes.Structure):
                _fields_ = [("cb", ctypes.c_ulong), ("page_faults", ctypes.c_ulong),
                            ("peak_ws", ctypes.c_size_t), ("ws", ctypes.c_size_t),
                            ("quota_peak_paged", ctypes.c_size_t), ("quota_paged", ctypes.c_size_t),
                            ("quota_peak_nonpaged", ctypes.c_size_t), ("quota_nonpaged", ctypes.c_size_t),
                            ("pagefile", ctypes.c_size_t), ("peak_pagefile", ctypes.c_size_t),
                            ("private", ctypes.c_size_t)]
            c = Counters()
            c.cb = ctypes.sizeof(Counters)
            ctypes.windll.psapi.GetProcessMemoryInfo(
                ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(c), c.cb)
            return round(c.ws / 1e6, 1)
        for line in open("/proc/self/status"):
            if line.startswith("VmRSS:"):
                return round(int(line.split()[1]) / 1024, 1)
    except Exception:   # noqa: BLE001
        pass
    try:
        import resource
        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    except Exception:   # noqa: BLE001
        return 0.0


def sys_mem_pct() -> float:
    """システム全体のメモリ使用率（%）。分からなければ 0"""
    try:
        if os.name == "nt":
            import ctypes

            class Mem(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = Mem()
            m.dwLength = ctypes.sizeof(Mem)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return float(m.dwMemoryLoad)
        total = avail = 0
        for line in open("/proc/meminfo"):
            if line.startswith("MemTotal:"):
                total = int(line.split()[1])
            elif line.startswith("MemAvailable:"):
                avail = int(line.split()[1])
        if total:
            return round(100.0 * (1 - avail / total), 1)
    except Exception:   # noqa: BLE001
        pass
    return 0.0


def sample(meter: CpuMeter) -> dict:
    return {"cpu_pct": meter.sample(), "proc_mb": proc_mb(), "sys_mem_pct": sys_mem_pct()}


def format_line(s: dict) -> str:
    cpu = "―" if s.get("cpu_pct") is None else f"{s['cpu_pct']:.0f}%"
    return (f"使用率 CPU {cpu} ・ アプリのメモリ {s.get('proc_mb', 0) / 1000:.1f} GB"
            f" ・ システムのメモリ {s.get('sys_mem_pct', 0):.0f}%")
