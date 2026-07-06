import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from build_helpers import resolve_bash, to_msys_path


class BuildHelperTests(unittest.TestCase):
    def test_env_override_selects_bash_without_hardcoded_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            bash = Path(tmp) / ("bash.exe" if os.name == "nt" else "bash")
            bash.write_text("", encoding="utf-8")

            resolved = resolve_bash(
                {"EMUGII_BASH": str(bash), "PATH": ""},
                is_compatible=lambda path: path == str(bash),
            )

            self.assertEqual(resolved, str(bash))

    def test_path_lookup_finds_bash_when_no_override_is_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            bash_name = "bash.exe" if os.name == "nt" else "bash"
            bash = Path(tmp) / bash_name
            bash.write_text("", encoding="utf-8")

            resolved = resolve_bash(
                {"PATH": tmp},
                is_compatible=lambda path: Path(path).resolve() == bash.resolve(),
            )

            self.assertEqual(Path(resolved).resolve(), bash.resolve())

    def test_path_lookup_skips_incompatible_bash_candidates(self):
        with tempfile.TemporaryDirectory() as bad_tmp:
            with tempfile.TemporaryDirectory() as good_tmp:
                bash_name = "bash.exe" if os.name == "nt" else "bash"
                bad_bash = Path(bad_tmp) / bash_name
                good_bash = Path(good_tmp) / bash_name
                bad_bash.write_text("", encoding="utf-8")
                good_bash.write_text("", encoding="utf-8")

                resolved = resolve_bash(
                    {"PATH": os.pathsep.join([bad_tmp, good_tmp])},
                    is_compatible=lambda path: Path(path).resolve()
                    == good_bash.resolve(),
                )

                self.assertEqual(Path(resolved).resolve(), good_bash.resolve())

    def test_env_override_rejects_incompatible_bash(self):
        with tempfile.TemporaryDirectory() as tmp:
            bash = Path(tmp) / ("bash.exe" if os.name == "nt" else "bash")
            bash.write_text("", encoding="utf-8")

            with self.assertRaisesRegex(FileNotFoundError, "not MSYS2/MINGW"):
                resolve_bash(
                    {"EMUGII_BASH": str(bash), "PATH": ""},
                    is_compatible=lambda path: False,
                )

    def test_windows_drive_path_converts_to_msys_path_without_lowercasing_rest(self):
        windows_path = "D:" + "\\Projects\\EmuGII\\build\\qemu"

        self.assertEqual(
            to_msys_path(windows_path),
            "/d/Projects/EmuGII/build/qemu",
        )

    def test_posix_path_is_left_as_posix_path(self):
        self.assertEqual(to_msys_path("/d/Projects/EmuGII"), "/d/Projects/EmuGII")

    def test_tracked_project_files_do_not_embed_windows_absolute_paths(self):
        repo_root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        binary_suffixes = {".bin", ".elf", ".exe", ".img", ".png", ".jpg", ".pdf"}
        offenders = []

        for relpath in result.stdout.splitlines():
            path = Path(relpath)
            full_path = repo_root / path
            if not full_path.exists():
                continue
            if path.parts and path.parts[0] == "ThirdParty":
                continue
            if path.suffix.lower() in binary_suffixes:
                continue

            text = full_path.read_text(encoding="utf-8", errors="ignore")
            if re.search(r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/]", text):
                offenders.append(relpath)

        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
