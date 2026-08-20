"""
builder.py — Stage 2 of the pipeline.

Compiles the C, C++ and Java sources with maximum optimization flags into
output/build/. Fails gracefully (records a diagnostic) when a compiler is
missing so the rest of the pipeline can continue with available languages.
"""
import os
import subprocess
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
DEFAULT_BUILD_DIR = PROJECT_ROOT.parent / "output" / "build"


def _run(cmd, timeout=300, cwd=None):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        return p.returncode, (p.stdout or ""), (p.stderr or "")
    except Exception as e:  # noqa: BLE001
        return -1, "", str(e)


def _tail(text, n=6):
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    return "\n      ".join(lines[-n:]) if lines else ""


def _exe(name):
    return f"{name}.exe" if os.name == "nt" else name


def build_c(toolchain, build_dir):
    cc = toolchain.get("c_compiler")
    if not cc:
        return {"ok": False, "reason": "no C compiler available"}
    src = SRC / "c" / "mandelbrot.c"
    out = build_dir / "c" / _exe("mandelbrot_c")
    out.parent.mkdir(parents=True, exist_ok=True)
    kind = cc.get("kind")
    if kind == "msvc":
        vcvars = toolchain.get("msvc_vcvars")
        cmd = ["cmd", "/c", "call", vcvars or "", "&&",
               "cl", "/nologo", "/O2", "/arch:AVX2", "/openmp", "/std:c11",
               "/D_CRT_SECURE_NO_WARNINGS", "/EHsc",
               str(src), "/Fe:" + str(out)]
    else:
        cmd = [cc["path"], "-O3", "-march=native", "-ffast-math", "-fopenmp",
               "-std=c11", "-Wno-unknown-pragmas",
               str(src), "-o", str(out)]
    rc, so, se = _run(cmd)
    if rc == 0 and out.exists():
        return {"ok": True, "exe": str(out), "compiler": cc.get("path"),
                "flags": " ".join(str(c) for c in cmd[1:])}
    return {"ok": False, "reason": _tail(se or so), "compiler": cc.get("path")}


def build_cpp(toolchain, build_dir):
    cppc = toolchain.get("cpp_compiler")
    if not cppc:
        return {"ok": False, "reason": "no C++ compiler available"}
    src = SRC / "cpp" / "mandelbrot.cpp"
    out = build_dir / "cpp" / _exe("mandelbrot_cpp")
    out.parent.mkdir(parents=True, exist_ok=True)
    kind = cppc.get("kind")
    if kind == "msvc":
        vcvars = toolchain.get("msvc_vcvars")
        cmd = ["cmd", "/c", "call", vcvars or "", "&&",
               "cl", "/nologo", "/O2", "/arch:AVX2", "/openmp", "/std:c++20",
               "/D_CRT_SECURE_NO_WARNINGS", "/EHsc",
               str(src), "/Fe:" + str(out)]
    else:
        cmd = [cppc["path"], "-O3", "-march=native", "-ffast-math", "-pthread",
               "-std=c++20", "-Wno-unknown-pragmas",
               str(src), "-o", str(out)]
    rc, so, se = _run(cmd)
    if rc == 0 and out.exists():
        return {"ok": True, "exe": str(out), "compiler": cppc.get("path"),
                "flags": " ".join(str(c) for c in cmd[1:])}
    return {"ok": False, "reason": _tail(se or so), "compiler": cppc.get("path")}


def build_java(toolchain, build_dir):
    javac = toolchain.get("javac")
    if not javac:
        return {"ok": False, "reason": "no javac available"}
    src = SRC / "java" / "Mandelbrot.java"
    out = build_dir / "java"
    out.mkdir(parents=True, exist_ok=True)
    cmd = [javac["path"], "-d", str(out), str(src)]
    rc, so, se = _run(cmd)
    if rc == 0 and (out / "Mandelbrot.class").exists():
        return {"ok": True, "class_dir": str(out), "compiler": javac.get("path"),
                "flags": " ".join(cmd[1:])}
    return {"ok": False, "reason": _tail(se or so), "compiler": javac.get("path")}


def build_all(toolchain, build_dir=None):
    build_dir = Path(build_dir or DEFAULT_BUILD_DIR)
    sys.path.insert(0, str(PROJECT_ROOT))
    builds = {
        "c": build_c(toolchain, build_dir),
        "cpp": build_cpp(toolchain, build_dir),
        "java": build_java(toolchain, build_dir),
    }
    return builds


if __name__ == "__main__":
    import json
    from preflight import detect_compilers
    tc = detect_compilers()
    print(json.dumps(build_all(tc), indent=2, default=str))
