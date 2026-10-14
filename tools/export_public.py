"""Make the public repository tree: tools, docs, glossary, texture specs and English-only
worksheets. No game data, no Japanese script text, no AI batch dumps, no internal notes.

  export_public.py OUT_DIR

OUT_DIR is cleared (except .git) and refilled, so it can be a clone of the public repo.
"""
import glob
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import hydrate

FILES = ["README.md", "LICENSE", "CHANGELOG.md", ".gitignore"]
DIRS = ["docs", "tools", "glossary", "textures", "data"]
SKIP = {"__pycache__"}


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    for name in os.listdir(out):
        if name == ".git":
            continue
        p = os.path.join(out, name)
        shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    for f in FILES:
        shutil.copy2(os.path.join(REPO, f), os.path.join(out, f))
    for d in DIRS:
        shutil.copytree(os.path.join(REPO, d), os.path.join(out, d),
                        ignore=shutil.ignore_patterns(*SKIP, "*.pyc"))
    hydrate.strip(os.path.join(REPO, "worksheets"), os.path.join(out, "worksheets"))
    n = sum(len(fs) for _, _, fs in os.walk(out) if ".git" not in _)
    print(f"exported {n} files to {out}")


if __name__ == "__main__":
    main()
