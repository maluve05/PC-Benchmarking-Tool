"""
hardware_info.py — Host hardware telemetry extractor.

Collects CPU model / cores / threads / clocks, cache hierarchy, vector
instruction support, RAM, and OS details. Best-effort across Windows,
Linux and macOS; every field degrades gracefully to "unknown".

Vector ISA detection: when a C compiler is available a tiny probe is
compiled and executed (most accurate). Otherwise falls back to OS
feature reporting (Linux /proc/cpuinfo, macOS sysctl) or "not detected".
"""
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import psutil
    HAVE_PSUTIL = True
except Exception:  # noqa: BLE001
    HAVE_PSUTIL = False

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run(cmd, timeout=60):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        return (p.stdout or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _ps(cmd):
    """Run a PowerShell command on Windows."""
    return _run(["powershell", "-NoProfile", "-Command", cmd])


def _os_basics():
    info = {
        "os_full": platform.platform(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "machine": platform.machine(),
        "processor_platform": platform.processor(),
        "python": platform.python_version(),
    }
    return info


def _cpu_cores():
    info = {"physical_cores": None, "logical_threads": None}
    if HAVE_PSUTIL:
        try:
            info["physical_cores"] = psutil.cpu_count(logical=False)
        except Exception:  # noqa: BLE001
            pass
        try:
            info["logical_threads"] = psutil.cpu_count(logical=True)
        except Exception:  # noqa: BLE001
            pass
    if info["logical_threads"] is None:
        info["logical_threads"] = os.cpu_count()
    return info


def _cpu_model():
    system = platform.system()
    if system == "Windows":
        out = _ps("(Get-CimInstance Win32_Processor).Name")
        return out or platform.processor() or "unknown"
    if system == "Linux":
        out = ""
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.lower().startswith("model name"):
                        out = line.split(":", 1)[1].strip()
                        break
        except OSError:
            pass
        return out or platform.processor() or "unknown"
    if system == "Darwin":
        return _run(["sysctl", "-n", "machdep.cpu.brand_string"]) or platform.processor() or "unknown"
    return platform.processor() or "unknown"


def _cpu_clocks():
    info = {"base_mhz": None, "boost_mhz": None, "current_mhz": None}
    system = platform.system()
    if system == "Windows":
        out = _ps("(Get-CimInstance Win32_Processor) | Select-Object MaxClockSpeed,CurrentClockSpeed | ConvertTo-Json")
        if out:
            try:
                import json
                d = json.loads(out)
                if isinstance(d, list):
                    d = d[0]
                info["boost_mhz"] = int(d.get("MaxClockSpeed") or 0) or None
                info["current_mhz"] = int(d.get("CurrentClockSpeed") or 0) or None
            except Exception:  # noqa: BLE001
                pass
    if HAVE_PSUTIL:
        try:
            f = psutil.cpu_freq()
            if f and f.current:
                info["current_mhz"] = int(f.current)
            if f and f.max:
                info["boost_mhz"] = info["boost_mhz"] or int(f.max)
        except Exception:  # noqa: BLE001
            pass
    return info


def _caches():
    info = {"l1d": None, "l1i": None, "l2": None, "l3": None}
    system = platform.system()
    if system == "Windows":
        out = _ps("Get-CimInstance Win32_Processor | Select-Object L2CacheSize,L3CacheSize | ConvertTo-Json")
        if out:
            try:
                import json
                d = json.loads(out)
                if isinstance(d, list):
                    d = d[0]
                info["l2"] = int(d.get("L2CacheSize") or 0) or None
                info["l3"] = int(d.get("L3CacheSize") or 0) or None
            except Exception:  # noqa: BLE001
                pass
        l1 = _ps("Get-CimInstance Win32_CacheMemory | Where-Object {$_.CacheType -eq 3} | Select-Object -First 1 -ExpandProperty MaxCacheSize")
        if l1:
            info["l1d"] = int(l1)
        l1i = _ps("Get-CimInstance Win32_CacheMemory | Where-Object {$_.CacheType -eq 4} | Select-Object -First 1 -ExpandProperty MaxCacheSize")
        if l1i:
            info["l1i"] = int(l1i)
        return info
    if system == "Linux":
        base = Path("/sys/devices/system/cpu/cpu0/cache")
        if base.exists():
            for idx in base.iterdir():
                try:
                    level = int((idx / "level").read_text().strip())
                    typ = (idx / "type").read_text().strip()
                    size = (idx / "size").read_text().strip()
                    kb = int(re.sub(r"[^0-9]", "", size))
                    if level == 1 and typ == "Data":
                        info["l1d"] = kb
                    elif level == 1 and typ == "Instruction":
                        info["l1i"] = kb
                    elif level == 2:
                        info["l2"] = kb
                    elif level == 3:
                        info["l3"] = kb
                except Exception:  # noqa: BLE001
                    pass
        return info
    if system == "Darwin":
        for key, field in (("l1d", "hw.l1dcachesize"), ("l1i", "hw.l1icachesize"),
                           ("l2", "hw.l2cachesize"), ("l3", "hw.l3cachesize")):
            v = _run(["sysctl", "-n", field])
            if v.isdigit():
                info[key] = int(v) // 1024
        return info
    return info


def _linux_cpuinfo_flags():
    flags = set()
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.lower().startswith("flags"):
                    flags = set(line.split(":", 1)[1].split())
                    break
    except OSError:
        pass
    return flags


def _vector_isa(toolchain):
    """Detect vector ISA. Prefer a compiled C probe; fall back to OS features."""
    isa = {"detected": False, "method": "not detected", "flags": []}

    # 1) Compiled probe (most accurate) — needs a C compiler.
    cc = toolchain.get("c_compiler")
    if cc:
        probe = r'''
#include <stdio.h>
int main(void) {
#ifdef __AVX512F__  printf("avx512 ");
#endif
#ifdef __AVX2__     printf("avx2 ");
#endif
#ifdef __AVX__      printf("avx ");
#endif
#ifdef __FMA__      printf("fma ");
#endif
#ifdef __SSE4_2__   printf("sse4.2 ");
#endif
#ifdef __SSE2__     printf("sse2 ");
#endif
#ifdef __ARM_NEON
#ifdef __aarch64__
    printf("neon ");
#else
    printf("neon ");
#endif
#endif
    printf("\n");
    return 0;
}
'''
        try:
            with tempfile.TemporaryDirectory() as tmp:
                src = Path(tmp) / "isa_probe.c"
                exe = Path(tmp) / ("isa_probe.exe" if os.name == "nt" else "isa_probe")
                src.write_text(probe)
                if cc["kind"] == "msvc":
                    rc = _run(["cmd", "/c", "call", toolchain.get("msvc_vcvars", ""),
                               "&&", "cl", "/nologo", "/O2", str(src), "/Fe:" + str(exe)], timeout=120)
                else:
                    rc = _run([cc["path"], "-O2", "-march=native", str(src), "-o", str(exe)], timeout=120)
                if rc and os.path.exists(exe):
                    flags = _run([str(exe)], timeout=30)
                    if flags:
                        isa["flags"] = flags.split()
                        isa["detected"] = True
                        isa["method"] = "compiled probe"
        except Exception:  # noqa: BLE001
            pass

    # 2) OS feature reporting fallback.
    if not isa["detected"]:
        system = platform.system()
        flags = set()
        if system == "Linux":
            flags = _linux_cpuinfo_flags()
        elif system == "Darwin":
            out = _run(["sysctl", "-n", "machdep.cpu.features", "machdep.cpu.leaf7_features"]).upper()
            flags = set(out.replace(",", " ").split())
        if flags:
            isa["flags"] = sorted(f for f in flags if f.lower() in
                                  ("avx512f", "avx2", "avx", "fma", "sse4_2", "sse2", "neon", "asimd"))
            isa["detected"] = True
            isa["method"] = "os features"

    # 3) Normalize into a friendly summary.
    f = [x.lower() for x in isa["flags"]]
    summary = []
    if any(x in f for x in ("avx512f", "avx512")):
        summary.append("AVX-512")
    if "avx2" in f:
        summary.append("AVX2")
    if "avx" in f:
        summary.append("AVX")
    if "fma" in f:
        summary.append("FMA")
    if "sse4_2" in f:
        summary.append("SSE4.2")
    if "sse2" in f:
        summary.append("SSE2")
    if "neon" in f or "asimd" in f:
        summary.append("NEON")
    isa["summary"] = ", ".join(summary) if summary else "not detected"
    return isa


def _ram():
    info = {"total_gb": None, "available_gb": None, "speed_mhz": None, "memory_type": None}
    if HAVE_PSUTIL:
        try:
            vm = psutil.virtual_memory()
            info["total_gb"] = round(vm.total / 2 ** 30, 2)
            info["available_gb"] = round(vm.available / 2 ** 30, 2)
        except Exception:  # noqa: BLE001
            pass
    system = platform.system()
    if system == "Windows":
        out = _ps("Get-CimInstance Win32_PhysicalMemory | Select-Object -First 1 Speed,SMBIOSMemoryType | ConvertTo-Json")
        if out:
            try:
                import json
                d = json.loads(out)
                if isinstance(d, list):
                    d = d[0]
                info["speed_mhz"] = int(d.get("Speed") or 0) or None
                smt = int(d.get("SMBIOSMemoryType") or 0)
                info["memory_type"] = {20: "DDR", 21: "DDR2", 24: "DDR3", 26: "DDR4", 34: "DDR5"}.get(smt, None)
            except Exception:  # noqa: BLE001
                pass
    elif system == "Linux":
        for line in _run(["cat", "/proc/meminfo"]).splitlines():
            if line.startswith("MemTotal"):
                try:
                    info["total_gb"] = round(int(line.split()[1]) / 1024 ** 2, 2)
                except Exception:  # noqa: BLE001
                    pass
    elif system == "Darwin":
        v = _run(["sysctl", "-n", "hw.memsize"])
        if v.isdigit():
            info["total_gb"] = round(int(v) / 2 ** 30, 2)
    return info


def _toolchain_summary(toolchain):
    out = {}
    for key in ("c_compiler", "cpp_compiler", "javac", "java"):
        c = toolchain.get(key)
        if c:
            out[key] = {"path": c.get("path"), "version": c.get("version")}
    return out


def collect_hardware(toolchain):
    info = {}
    info.update(_os_basics())
    info.update(_cpu_cores())
    info["cpu_model"] = _cpu_model()
    info.update(_cpu_clocks())
    info.update(_caches())
    info["vector_isa"] = _vector_isa(toolchain)
    info["ram"] = _ram()
    info["toolchain"] = _toolchain_summary(toolchain)
    info["hostname"] = platform.node()
    return info


def format_hardware_table(info):
    """Render the hardware profile as a markdown table for the report."""
    rows = [
        ("Host", info.get("hostname", "unknown")),
        ("Operating System", f"{info.get('os_full', 'unknown')} (release {info.get('os_release', '?')})"),
        ("Architecture", info.get("machine", "unknown")),
        ("CPU Model", info.get("cpu_model", "unknown")),
        ("Physical Cores", str(info.get("physical_cores", "unknown"))),
        ("Logical Threads", str(info.get("logical_threads", "unknown"))),
        ("Base / Boost Clock", _fmt_clocks(info)),
        ("L1d / L1i Cache", f"{_fmt_kb(info.get('l1d'))} / {_fmt_kb(info.get('l1i'))}"),
        ("L2 Cache", _fmt_kb(info.get("l2"))),
        ("L3 Cache", _fmt_kb(info.get("l3"))),
        ("Vector ISA", info.get("vector_isa", {}).get("summary", "not detected")),
        ("System RAM", _fmt_ram(info)),
        ("Python", info.get("python", "unknown")),
    ]
    for key, label in (("c_compiler", "C Compiler"), ("cpp_compiler", "C++ Compiler"),
                       ("javac", "Java Compiler"), ("java", "Java Runtime")):
        t = info.get("toolchain", {}).get(key)
        rows.append((label, f"{t['path']} ({t['version']})" if t else "not available"))
    lines = ["| Metric | Value |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in rows]
    return "\n".join(lines)


def _fmt_clocks(info):
    base, boost, cur = info.get("base_mhz"), info.get("boost_mhz"), info.get("current_mhz")
    parts = []
    if base:
        parts.append(f"base {base} MHz")
    if boost:
        parts.append(f"boost {boost} MHz")
    if cur:
        parts.append(f"current {cur} MHz")
    return ", ".join(parts) if parts else "unknown"


def _fmt_kb(kb):
    if kb is None:
        return "unknown"
    if kb >= 1024:
        return f"{kb / 1024:.1f} MB"
    return f"{kb} KB"


def _fmt_ram(info):
    ram = info.get("ram", {})
    parts = []
    if ram.get("total_gb"):
        parts.append(f"{ram['total_gb']} GB total")
    if ram.get("available_gb"):
        parts.append(f"{ram['available_gb']} GB available")
    if ram.get("speed_mhz"):
        parts.append(f"{ram['speed_mhz']} MHz")
    if ram.get("memory_type"):
        parts.append(ram["memory_type"])
    return ", ".join(parts) if parts else "unknown"


if __name__ == "__main__":
    import json
    tc = {"c_compiler": None}
    hw = collect_hardware(tc)
    print(json.dumps(hw, indent=2, default=str))
    print()
    print(format_hardware_table(hw))
