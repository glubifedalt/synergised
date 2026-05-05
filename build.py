"""
build.py – Synergy Teacher Dashboard
Run this instead of calling pyinstaller directly.

  Windows:   double-click build.py  (or  python build.py)
  macOS/Linux:  python3 build.py

It automatically:
  • cd's to the folder containing this script (fixes "no directory" errors)
  • Checks Python version
  • Installs / upgrades required packages if missing
  • Detects PyInstaller version and refuses to use an incompatible one
  • Runs PyInstaller with the correct arguments
  • Tells you exactly where the output file is
"""

import sys
import os
import subprocess
import shutil
from pathlib import Path

# ── Always work from the directory this script lives in ──────────────────
HERE = Path(__file__).resolve().parent
os.chdir(HERE)
print(f"Working directory: {HERE}\n")

# ── Python version check ──────────────────────────────────────────────────
if sys.version_info < (3, 10):
    print(f"❌  Python 3.10+ required (you have {sys.version})")
    sys.exit(1)

print(f"✅  Python {sys.version_info.major}.{sys.version_info.minor}")

# ── Helper: run a command and stream output ───────────────────────────────
def run(cmd, **kwargs):
    print(f"\n▶  {' '.join(str(c) for c in cmd)}\n")
    result = subprocess.run(cmd, **kwargs)
    if result.returncode != 0:
        print(f"\n❌  Command failed (exit {result.returncode})")
        sys.exit(result.returncode)
    return result

# ── Install / upgrade build dependencies ─────────────────────────────────
print("Checking build dependencies…")
run([sys.executable, "-m", "pip", "install", "--upgrade",
     "pyinstaller>=6.0",
     "pyinstaller-hooks-contrib"])

# ── Verify PyInstaller version ────────────────────────────────────────────
result = subprocess.run(
    [sys.executable, "-m", "PyInstaller", "--version"],
    capture_output=True, text=True
)
pi_ver = result.stdout.strip()
print(f"✅  PyInstaller {pi_ver}")

major = int(pi_ver.split(".")[0]) if pi_ver else 0
if major < 6:
    print(f"❌  PyInstaller 6+ required (got {pi_ver}). Run:")
    print("       pip install --upgrade pyinstaller")
    sys.exit(1)

# ── Check main.py exists ──────────────────────────────────────────────────
if not (HERE / "main.py").exists():
    print(f"❌  main.py not found in {HERE}")
    print("    Make sure you're running build.py from inside the synergy_tool folder.")
    sys.exit(1)
print("✅  main.py found")

# ── Clean previous build artefacts ───────────────────────────────────────
for d in ["build", "dist"]:
    p = HERE / d
    if p.exists():
        print(f"   Removing old {d}/…")
        shutil.rmtree(p)

# ── Run PyInstaller ───────────────────────────────────────────────────────
spec = HERE / "synergy_tool.spec"
run([
    sys.executable, "-m", "PyInstaller",
    str(spec),
    "--noconfirm",
    "--clean",
    f"--distpath={HERE / 'dist'}",
    f"--workpath={HERE / 'build'}",
    f"--specpath={HERE}",
])

# ── Report output ─────────────────────────────────────────────────────────
exe_name = "SynergyDashboard.exe" if sys.platform == "win32" else "SynergyDashboard"
exe_path = HERE / "dist" / exe_name

print("\n" + "═" * 60)
if exe_path.exists():
    size_mb = exe_path.stat().st_size / 1_048_576
    print(f"✅  Build successful!")
    print(f"   Output: {exe_path}")
    print(f"   Size:   {size_mb:.1f} MB")
    print()
    print("   Copy SynergyDashboard.exe anywhere to use it.")
    print("   No Python installation needed on the target machine.")
else:
    print("⚠  Build finished but output file not found where expected.")
    print(f"   Check inside:  {HERE / 'dist'}")
print("═" * 60 + "\n")

# ── Optionally open the output folder ────────────────────────────────────
dist_dir = HERE / "dist"
if dist_dir.exists():
    if sys.platform == "win32":
        os.startfile(dist_dir)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(dist_dir)])
    # Linux: don't auto-open, just print the path above
