"""
Refresh the published figures and put them live, in one command.

    python scripts/publish_site.py
    python scripts/publish_site.py --threshold 5     # before real patient data
    python scripts/publish_site.py --skip-export     # rebuild without re-querying

Three steps: export the figures from the database, build the static site around
them, push the result to the branch GitHub Pages serves.

There is a workflow in .github/workflows that does the same thing on every
push. It cannot run while the GitHub account is locked for billing, which is
why this exists -- GitHub Pages' own build is not blocked by that lock, so
pushing the built site still works.

The base path matters and is easy to get wrong. A GitHub Pages project site is
served from /<repo>, not from a domain root, so the prefix has to be baked in
at build time. On Windows, Git Bash rewrites a value beginning with a slash
into a Windows path -- which is why this sets the environment variable from
Python rather than leaving it to a shell.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
OUT = WEB / "out"

#: Where the site is served from. Empty for a root domain; "/GH-AMR-Dashboard"
#: for the GitHub Pages project site.
BASE_PATH = os.environ.get("NEXT_PUBLIC_BASE_PATH", "/GH-AMR-Dashboard")

#: The branch GitHub Pages serves, and where it came from.
BRANCH = os.environ.get("PAGES_BRANCH", "gh-pages")
REMOTE = os.environ.get("PAGES_REMOTE",
                        "https://github.com/JesseAnak7534/GH-AMR-Dashboard.git")


def run(command: list[str], cwd: Path, env: dict | None = None) -> None:
    """Run a step, and stop the moment one fails.

    Carrying on after a failed build would publish the previous build over
    again and report success, which is worse than stopping: the figures would
    silently not be the ones just exported.
    """
    printable = " ".join(command)
    print(f"\n$ {printable}")
    result = subprocess.run(command, cwd=cwd, env=env)
    if result.returncode != 0:
        raise SystemExit(f"\nFailed: {printable}\nNothing was published.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--threshold", type=int, default=None,
                        help="smallest publishable cell passed to the export")
    parser.add_argument("--skip-export", action="store_true",
                        help="rebuild and publish the figures already exported")
    parser.add_argument("--dry-run", action="store_true",
                        help="export and build, but do not publish")
    args = parser.parse_args()

    if not args.skip_export:
        export = [sys.executable, str(ROOT / "scripts" / "export_public_data.py")]
        if args.threshold is not None:
            export += ["--threshold", str(args.threshold)]
        run(export, cwd=ROOT)

    # npm on Windows is a .cmd shim, which subprocess will not find by name.
    npm = shutil.which("npm") or "npm"

    env = dict(os.environ)
    env["NEXT_PUBLIC_BASE_PATH"] = BASE_PATH
    run([npm, "run", "build"], cwd=WEB, env=env)

    if not (OUT / "index.html").exists():
        raise SystemExit("The build produced no index.html. Nothing published.")

    # Pages runs the output through Jekyll without this, and Jekyll ignores
    # every directory beginning with an underscore -- including _next, where
    # the whole bundle lives. The site would serve as unstyled HTML.
    (OUT / ".nojekyll").write_text("", encoding="utf-8")

    if args.dry_run:
        print(f"\nBuilt into {OUT}. Not published (--dry-run).")
        return 0

    # A throwaway repository whose only commit is this build. The branch is
    # force-pushed, so its history is the deployment history and nothing else.
    with tempfile.TemporaryDirectory() as work:
        git_dir = Path(work) / "git"
        base = ["git", f"--git-dir={git_dir}", f"--work-tree={OUT}"]
        run(base + ["init", "-q", "-b", BRANCH], cwd=OUT)
        run(base + ["config", "user.name", "AMRSS publisher"], cwd=OUT)
        run(base + ["config", "user.email", "jesseanak98@gmail.com"], cwd=OUT)
        run(base + ["add", "-A"], cwd=OUT)
        run(base + ["commit", "-q", "-m", "Publish the public surveillance site"],
            cwd=OUT)
        run(base + ["push", "--force", "-q", REMOTE, BRANCH], cwd=OUT)

    print("\nPublished. GitHub Pages usually serves the new build within a "
          "minute or two:")
    print("  https://jesseanak7534.github.io/GH-AMR-Dashboard/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
