import os
import re
import shutil
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


def resolve_bash(env=None):
    """Resolve the shell used for the QEMU POSIX build steps."""
    if env is None:
        env = os.environ

    for name in ("EMUGII_BASH", "MSYS2_BASH"):
        value = env.get(name)
        if value:
            bash = Path(value)
            if not bash.exists():
                raise FileNotFoundError(f"{name} points to a missing bash: {value}")
            return str(bash)

    bash = shutil.which("bash", path=env.get("PATH"))
    if bash:
        return bash

    raise FileNotFoundError(
        "bash was not found. Add MSYS2 bash to PATH or set EMUGII_BASH."
    )
