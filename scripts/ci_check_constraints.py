#!/usr/bin/env python3
"""CI guard: every installed package must match its constraints.txt pin.

constraints.txt exists so the bundle CI ships is the exact dependency set
that was tested (BRIEF S6z/S6aa: an unpinned transitive numpy 2.x reached
a pilot tester's machine and crashed at startup). pip constraints only
bind packages pip itself installs in that run, so a transitive dep that
somehow arrives outside the constrained install -- or a package missing
from constraints.txt entirely (e.g. a platform-only dep the cross-platform
resolve missed) -- would still float silently. This check closes that:
after the install step, every importable distribution must either match
its pin or be explicitly allowlisted below.

Run on every CI build, all three platforms: python scripts/ci_check_constraints.py
"""
import sys
import sysconfig
import pathlib
from importlib import metadata

# Present in CI environments for reasons outside requirements.txt (runner
# image / venv tooling); not shipped by the PyInstaller bundle's collect
# list, so their versions floating is acceptable and expected.
ALLOWED_UNPINNED_PREFIXES = (
    "pip", "setuptools", "wheel", "pyinstaller-hooks-contrib",
    "altgraph", "pefile", "macholib", "pywin32",  # pyinstaller's own deps
    # Preinstalled pipx toolchain on GitHub's Windows runner image --
    # never imported by the app, never collected by the spec (confirmed
    # by the v0.1.18 run: present before our install step ran at all).
    "argcomplete", "userpath", "platformdirs", "pipx",
)


def normalize(name: str) -> str:
    return name.lower().replace("_", "-").replace(".", "-")


def main() -> int:
    constraints_path = pathlib.Path(__file__).resolve().parent.parent / "constraints.txt"
    pins = {}
    for line in constraints_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, version = line.split("==")
        pins[normalize(name)] = version

    failures = []
    unpinned = []
    # Enumerate only THIS environment's own purelib (where pip just
    # installed to), not inherited system-site packages -- the Linux CI
    # venv is deliberately --system-site-packages for gi/GTK (see
    # build.yml), and on Debian/Ubuntu site.getsitepackages() can include
    # the system dist-packages dir too, which would report apt's copy of
    # a package alongside the pinned venv copy that actually shadows it.
    seen_pinned = set()
    for dist in metadata.distributions(path=[sysconfig.get_paths()["purelib"]]):
        name = normalize(dist.metadata["Name"])
        if name in pins:
            seen_pinned.add(name)
            if dist.version != pins[name]:
                failures.append(f"{name}: installed {dist.version} != pinned {pins[name]}")
        elif not any(name.startswith(p) for p in ALLOWED_UNPINNED_PREFIXES):
            unpinned.append(f"{name}=={dist.version}")

    # Second pass over the FULL import path: a system-site package (the
    # Linux venv inherits them) can satisfy a transitive requirement so
    # pip never installs the pinned version at all -- yet PyInstaller
    # would freeze that system copy. Whatever version a pinned package
    # actually resolves to at import time must match its pin. A pin not
    # found anywhere is fine (platform-only, e.g. pyobjc on Linux).
    for name, pinned_version in pins.items():
        if name in seen_pinned:
            continue
        try:
            found = metadata.version(name)
        except metadata.PackageNotFoundError:
            continue
        if found != pinned_version:
            failures.append(
                f"{name}: resolves to {found} on the import path "
                f"!= pinned {pinned_version} (system-site shadowing?)")

    if failures or unpinned:
        for f in failures:
            print(f"MISMATCH  {f}", file=sys.stderr)
        for u in unpinned:
            print(f"UNPINNED  {u} (add to constraints.txt or the allowlist)",
                  file=sys.stderr)
        print("FAIL: the environment about to be bundled does not match "
              "constraints.txt -- an untested version would ship.", file=sys.stderr)
        return 1

    print(f"OK: all {len(pins)} constraint pins honored; no unexpected "
          "unpinned packages installed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
