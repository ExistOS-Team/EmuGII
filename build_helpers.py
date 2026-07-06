import os
import re
import subprocess
from pathlib import Path


def to_msys_path(path):
    """Convert a Windows drive path to the MSYS2 /d/... form."""
    path_text = os.fspath(path).replace("\\", "/")
    match = re.match(r"^([A-Za-z]):/?(.*)$", path_text)
    if not match:
        return path_text

    drive = match.group(1).lower()
    rest = match.group(2)
    if rest:
        return f"/{drive}/{rest}"
    return f"/{drive}"


def _path_bash_candidates(path):
    names = ("bash.exe", "bash") if os.name == "nt" else ("bash",)
    seen = set()

    for directory in (path or "").split(os.pathsep):
        if not directory:
            continue

        for name in names:
            candidate = Path(directory) / name
            if not candidate.is_file():
                continue

            key = os.path.normcase(os.path.abspath(candidate))
            if key in seen:
                continue
            seen.add(key)
            yield str(candidate)


def _is_msys_compatible_bash(bash):
    probe = (
        'case "$(uname -s 2>/dev/null)" in '
        'MINGW*|MSYS*) ;; *) exit 1 ;; esac; '
        'command -v cygpath >/dev/null'
    )
    try:
        result = subprocess.run(
            [bash, "-lc", probe],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False

    return result.returncode == 0


def _check_compatible_bash(bash, is_compatible):
    if is_compatible(bash):
        return bash
    raise FileNotFoundError(f"bash is not MSYS2/MINGW compatible: {bash}")


def resolve_bash(env=None, is_compatible=None):
    """Resolve the shell used for the QEMU POSIX build steps."""
    if env is None:
        env = os.environ
    if is_compatible is None:
        is_compatible = _is_msys_compatible_bash

    for name in ("EMUGII_BASH", "MSYS2_BASH"):
        value = env.get(name)
        if value:
            bash = Path(value)
            if not bash.exists():
                raise FileNotFoundError(f"{name} points to a missing bash: {value}")
            return _check_compatible_bash(str(bash), is_compatible)

    for bash in _path_bash_candidates(env.get("PATH")):
        if is_compatible(bash):
            return bash

    raise FileNotFoundError(
        "MSYS2/MINGW bash was not found. Add it to PATH or set EMUGII_BASH."
    )
