"""前の回が落ちたかを、残った処理の番号から確かめる"""
from __future__ import annotations

import os
import sys


def pid_alive(pid: int) -> bool:
    """その番号のプロセスがまだ動いているか。Windows の os.kill は相手を止めてしまうので使わない"""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return bool(ok) and code.value == 259   # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def crashed_before(store) -> bool:
    """前の起動が正しく閉じずに終わったか。印には起動したプロセスの番号を残す。

    前は印が 0/1 だけで、固まって止められると 1 が残り、正しく 1 回閉じるまで起動のたびに落ちた扱いになった。
    番号が今も動いている（2 つ目の起動）なら落ちた扱いにしない。昔の印の 1 は落ちた扱い
    """
    try:
        prev = int(store.value("running", 0) or 0)
    except (TypeError, ValueError):
        return True
    if prev == 0:
        return False
    return prev == 1 or prev != os.getpid() and not pid_alive(prev)
