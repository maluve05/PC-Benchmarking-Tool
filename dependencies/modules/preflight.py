"""
preflight.py — Stage 1 of the pipeline.

1. Validates the Python interpreter.
2. Auto-installs missing packages listed in requirements.txt (tolerant:
   a package that fails to install is recorded as unavailable, never fatal).
3. Detects the native toolchain: gcc, g++, clang, clang++, MSVC cl,
   javac + java, and reports versions.

Returns a `toolchain` dict consumed by builder.py / report_generator.py.
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = PROJECT_ROOT / "requirements.txt"


def _run(cmd, timeout=120, **kw):
    """Run a command, return (returncode, stdout, stderr). Never raises."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kw)
        return p.returncode, p.stdout or "", p.stderr or ""
    except Exception as e:  # noqa: BLE001
        return -1, "", str(e)


def python_version_check():
    info = {
        "version": sys.version.split()[0],
        "executable": sys.executable,
        "ok": sys.version_info >= (3, 8),
    }
    if not info["ok"]:
        print(f"  [WARN] Python >= 3.8 recommended (found {info['version']})")
    return info


def install_requirements(quiet=True):
    """Install every package in requirements.txt individually (tolerant)."""
    if not REQUIREMENTS.exists():
        print("  [WARN] requirements.txt not found — skipping dependency install")
        return {}
    pkgs = [ln.strip() for ln in REQUIREMENTS.read_text().splitlines()
            if ln.strip() and not ln.strip().startswith("#")]
    installed = {}
    for pkg in pkgs:
        name = re.split(r"[<>=!~ ]", pkg)[0]
        # Skip if already importable (fast path, avoids pip chatter).
        if _importable(name):
            installed[pkg] = "already-present"
            continue
        print(f"  [pip] installing {pkg} ...")
        rc, out, err = _run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", pkg], timeout=600)
        if rc == 0:
            installed[pkg] = "installed"
        else:
            installed[pkg] = f"FAILED ({_last_line(err) or _last_line(out)})"
            print(f"  [WARN] could not install {pkg}: {installed[pkg]}")
    return installed


_PKG_MODULE = {"pillow": "PIL"}


def _importable(name):
    mod = _PKG_MODULE.get(name, name)
    try:
        __import__(mod)
        return True
    except Exception:  # noqa: BLE001
        return False


def _last_line(s):
    return (s or "").strip().splitlines()[-1] if (s or "").strip() else ""


def _probe_version(exe, args=("--version",)):
    rc, out, err = _run([exe, *args], timeout=30)
    if rc != 0:
        rc, out, err = _run([exe, "-version"], timeout=30)
    text = (out or err).strip().splitlines()
    return text[0][:160] if text else ""


def detect_compilers():
    """Detect available native compilers + JVM. Returns toolchain dict."""
    toolchain = {
        "gcc": None, "g++": None, "clang": None, "clang++": None,
        "cl": None, "cl_exe": None, "javac": None, "java": None,
        "msvc_vcvars": None, "c_compiler": None, "cpp_compiler": None,
    }

    candidates = {
        "gcc": ["gcc", "cc"],
        "g++": ["g++", "c++"],
        "clang": ["clang", "clang-18", "clang-17", "clang-16"],
        "clang++": ["clang++", "clang++-18", "clang++-17", "clang++-16"],
        "cl": ["cl"],
        "javac": ["javac"],
        "java": ["java"],
    }
    for key, names in candidates.items():
        for name in names:
            path = shutil.which(name)
            if path:
                toolchain[key] = {"path": path, "version": _probe_version(path)}
                break

    # MSVC via vswhere (Visual Studio Build Tools / VS)
    vswhere = (
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    )
    if vswhere.exists():
        rc, out, _ = _run([str(vswhere), "-latest", "-products", "*",
                           "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                           "-property", "installationPath"], timeout=60)
        vs_path = out.strip() if rc == 0 else ""
        if vs_path:
            vcvars = Path(vs_path) / "VC" / "Auxiliary" / "Build" / "vcvars64.bat"
            if vcvars.exists():
                toolchain["msvc_vcvars"] = str(vcvars)
                # cl.exe lives under VC/Tools/MSVC/<ver>/bin/Hostx64/x64/cl.exe
                msvc_tools = Path(vs_path) / "VC" / "Tools" / "MSVC"
                if msvc_tools.exists():
                    versions = sorted(msvc_tools.iterdir(), reverse=True)
                    for ver in versions:
                        cl = ver / "bin" / "Hostx64" / "x64" / "cl.exe"
                        if cl.exists():
                            toolchain["cl_exe"] = str(cl)
                            break

    # Decide the "best" C/C++ compiler (MSVC cl needs vcvars, so it is last resort).
    for key, label in (("clang", "clang"), ("gcc", "gcc")):
        if toolchain[key]:
            toolchain["c_compiler"] = {**toolchain[key], "kind": label}
            break
    else:
        if toolchain["cl"] or toolchain["cl_exe"]:
            toolchain["c_compiler"] = {
                "path": toolchain["cl_exe"] or toolchain["cl"]["path"],
                "version": (toolchain["cl"] or {}).get("version", "MSVC"),
                "kind": "msvc",
            }

    for key, label in (("clang++", "clang++"), ("g++", "g++")):
        if toolchain[key]:
            toolchain["cpp_compiler"] = {**toolchain[key], "kind": label}
            break
    else:
        if toolchain["c_compiler"] and toolchain["c_compiler"]["kind"] == "msvc":
            toolchain["cpp_compiler"] = {**toolchain["c_compiler"], "kind": "msvc"}
        else:
            toolchain["cpp_compiler"] = toolchain["c_compiler"]

    return toolchain


def run_preflight():
    print("── Stage 1 · Preflight & Environment Setup ──────────────────────")
    pyinfo = python_version_check()
    print(f"  Python {pyinfo['version']} ({pyinfo['executable']})")

    print("  Installing missing Python packages ...")
    installed = install_requirements()
    missing = [p for p, v in installed.items() if v.startswith("FAILED")]
    if missing:
        print(f"  [WARN] {len(missing)} package(s) unavailable: {', '.join(missing)}")

    print("  Detecting native toolchain ...")
    toolchain = detect_compilers()
    for key, label in (("c_compiler", "C compiler"), ("cpp_compiler", "C++ compiler")):
        c = toolchain[key]
        print(f"  {label:<14}: {c['path'] if c else 'NOT FOUND'}"
              f"{'  (' + c['version'] + ')' if c else ''}")
    for key in ("javac", "java"):
        c = toolchain[key]
        print(f"  {key:<15}: {c['path'] if c else 'NOT FOUND'}"
              f"{'  (' + c['version'] + ')' if c else ''}")

    available = {
        "c": toolchain["c_compiler"] is not None,
        "cpp": toolchain["cpp_compiler"] is not None,
        "java": toolchain["javac"] is not None and toolchain["java"] is not None,
        "numba": _importable("numba"),
    }
    if not any(available.values()):
        print("  [INFO] No native compilers detected — Python-only run.")
    return {"python": pyinfo, "toolchain": toolchain, "installed": installed, "available": available}


if __name__ == "__main__":
    info = run_preflight()
    import json
    print(json.dumps(info, indent=2, default=str))
