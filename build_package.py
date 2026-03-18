import os
import re
import shutil
import sys
import subprocess


BUILD_DIR = "dist_pkg"
PKG_DIR = os.path.join(BUILD_DIR, "tokenscope")
CORE_SRC = "core"
SDK_SRC = "sdk"
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def clean():
    for d in [BUILD_DIR, "dist", "tokenscope.egg-info"]:
        if os.path.exists(d):
            shutil.rmtree(d)
    print("Cleaned build dirs")


def copy_core():
    dst = os.path.join(PKG_DIR, "core")
    shutil.copytree(CORE_SRC, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "tests"))
    open(os.path.join(dst, "__init__.py"), "w").close()
    print(f"Copied core/ → {dst}")


def copy_sdk():
    os.makedirs(PKG_DIR, exist_ok=True)
    for filename in ["client.py", "reporter.py"]:
        shutil.copy(os.path.join(SDK_SRC, filename), os.path.join(PKG_DIR, filename))
    print(f"Copied sdk/client.py, sdk/reporter.py → {PKG_DIR}/")


def fix_imports():
    core_dir = os.path.join(PKG_DIR, "core")
    pkg_files = [
        os.path.join(PKG_DIR, "client.py"),
        os.path.join(PKG_DIR, "reporter.py"),
    ]
    core_files = [
        os.path.join(core_dir, f)
        for f in os.listdir(core_dir)
        if f.endswith(".py")
    ]
    for filepath in pkg_files + core_files:
        with open(filepath, "r") as f:
            content = f.read()
        updated = re.sub(r'\bfrom core\.', 'from tokenscope.core.', content)
        updated = re.sub(r'\bimport core\.', 'import tokenscope.core.', updated)
        updated = re.sub(r'sys\.path\.insert\(0.*?\)\n', '', updated)
        if updated != content:
            with open(filepath, "w") as f:
                f.write(updated)
    print("Fixed imports in all package files")


def write_init():
    init_path = os.path.join(PKG_DIR, "__init__.py")
    with open(init_path, "w") as f:
        f.write('from tokenscope.client import TokenScope, TokenScopeSession\n\n')
        f.write('__version__ = "0.1.0"\n')
        f.write('__all__ = ["TokenScope", "TokenScopeSession"]\n')
    print(f"Wrote {init_path}")


def build():
    os.makedirs("dist", exist_ok=True)

    print("Building wheel...")
    r1 = subprocess.run(
        [sys.executable, "-m", "pip", "wheel", ".",
         "--no-deps", "--no-build-isolation", "-w", "dist"],
        cwd=PROJECT_ROOT,
    )
    if r1.returncode != 0:
        sys.exit(1)

    print("Building sdist...")
    r2 = subprocess.run(
        [sys.executable, "-m", "build", "--sdist", "--no-isolation"],
        cwd=PROJECT_ROOT,
    )
    if r2.returncode != 0:
        print("sdist failed, wheel is still available in dist/")

    print("\nBuild complete — dist/ ready")
    for f in os.listdir("dist"):
        print(f"  dist/{f}")


if __name__ == "__main__":
    print("\nBuilding tokenscope package...\n")
    clean()
    copy_core()
    copy_sdk()
    fix_imports()
    write_init()

    if "--build" in sys.argv:
        build()
        print("\n✅ Package ready")
        print("   To publish: twine upload dist/*")
    else:
        print("\n✅ Package assembled in dist_pkg/")
        print("   To build wheels: python build_package.py --build")
        print("   To publish:      twine upload dist/*")