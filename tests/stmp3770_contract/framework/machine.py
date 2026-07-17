import asyncio
import os
import re
import socket
import sys
from contextlib import asynccontextmanager

from framework.constants import QEMU_BINARY, QEMU_CWD


_repo_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
import build_helpers


def _qemu_env():
    """Return an env dict with MSYS2/MINGW runtime directories on PATH."""
    env = os.environ.copy()
    try:
        bash = build_helpers.resolve_bash(env)
        entries = build_helpers.runtime_path_entries_for_bash(bash)
        if entries:
            env["PATH"] = build_helpers.prepend_path_entries(env.get("PATH", ""), entries)
            env.setdefault("MSYSTEM", "MINGW64")
            env.setdefault("CHERE_INVOKING", "1")
    except FileNotFoundError:
        pass
    return env


def reserve_port():
    """Reserve an ephemeral TCP port and release it for QEMU to bind."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    return port


class QTestMachine:
    """Async QEMU qtest protocol driver for STMP3770."""

    def __init__(self, extra_args=None):
        self.port = reserve_port()
        self.extra_args = list(extra_args or [])
        self._proc = None
        self._reader = None
        self._writer = None
        self._stderr_buf = ""
        self._stderr_task = None
        self._env = _qemu_env()

    async def start(self):
        """Spawn QEMU and connect to the qtest socket."""
        self._proc = await asyncio.create_subprocess_exec(
            QEMU_BINARY,
            "-M", "stmp3770",
            "-display", "none",
            "-monitor", "none",
            "-serial", "none",
            "-chardev",
            f"socket,id=qtest,host=127.0.0.1,port={self.port},server=on,wait=off",
            "-accel", "qtest",
            "-qtest", "chardev:qtest",
            *self.extra_args,
            cwd=QEMU_CWD,
            stdout=asyncio.subprocess.DEVNULL,
            stdin=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            env=self._env,
        )
        self._stderr_task = asyncio.create_task(self._drain_stderr())
        await self.connect()

    async def connect(self, timeout_ms=5000):
        deadline = asyncio.get_event_loop().time() + timeout_ms / 1000.0
        while True:
            try:
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection("127.0.0.1", self.port),
                    timeout=1.0,
                )
                return
            except (asyncio.TimeoutError, OSError, ConnectionRefusedError):
                if asyncio.get_event_loop().time() >= deadline:
                    break
                await asyncio.sleep(0.05)
        raise RuntimeError(f"Timed out connecting qtest socket. stderr={self._stderr_buf}")

    async def _drain_stderr(self):
        while True:
            try:
                data = await self._proc.stderr.read(4096)
            except Exception:
                break
            if not data:
                break
            self._stderr_buf += data.decode("utf-8", errors="replace")

    @property
    def stderr(self) -> str:
        return self._stderr_buf

    async def _readline(self, timeout_ms=5000):
        line = await asyncio.wait_for(
            self._reader.readuntil(b"\n"), timeout=timeout_ms / 1000.0
        )
        text = line.decode("utf-8", errors="replace").rstrip("\r\n")
        return text

    async def cmd(self, command):
        self._writer.write(f"{command}\n".encode())
        await self._writer.drain()
        while True:
            line = await self._readline()
            if not line:
                continue
            if line.startswith("IRQ "):
                continue
            return line

    async def readl(self, addr):
        resp = await self.cmd(f"readl 0x{addr:x}")
        if not re.fullmatch(r"OK 0x[0-9a-fA-F]+", resp):
            raise AssertionError(f"Unexpected readl response: {resp}")
        return int(resp.split()[1], 16)

    async def readw(self, addr):
        resp = await self.cmd(f"readw 0x{addr:x}")
        if not re.fullmatch(r"OK 0x[0-9a-fA-F]+", resp):
            raise AssertionError(f"Unexpected readw response: {resp}")
        return int(resp.split()[1], 16)

    async def readb(self, addr):
        resp = await self.cmd(f"readb 0x{addr:x}")
        if not re.fullmatch(r"OK 0x[0-9a-fA-F]+", resp):
            raise AssertionError(f"Unexpected readb response: {resp}")
        return int(resp.split()[1], 16)

    async def writel(self, addr, value):
        resp = await self.cmd(f"writel 0x{addr:x} 0x{value:x}")
        if resp != "OK":
            raise AssertionError(f"Unexpected writel response: {resp}")

    async def writew(self, addr, value):
        resp = await self.cmd(f"writew 0x{addr:x} 0x{value:x}")
        if resp != "OK":
            raise AssertionError(f"Unexpected writew response: {resp}")

    async def writeb(self, addr, value):
        resp = await self.cmd(f"writeb 0x{addr:x} 0x{value:x}")
        if resp != "OK":
            raise AssertionError(f"Unexpected writeb response: {resp}")

    async def clock_step(self, ns=None):
        if ns is None:
            resp = await self.cmd("clock_step")
        else:
            resp = await self.cmd(f"clock_step {ns}")
        if not resp.startswith("OK "):
            raise AssertionError(f"Unexpected clock_step response: {resp}")

    async def set_irq_in(self, qom_path, name, num, level):
        gpio_name = name or "unnamed-gpio-in"
        resp = await self.cmd(
            f"set_irq_in {qom_path} {gpio_name} {num} {level}"
        )
        if resp != "OK":
            raise AssertionError(f"Unexpected set_irq_in response: {resp}")

    async def close(self):
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
        if self._proc and self._proc.returncode is None:
            self._proc.kill()
            await self._proc.wait()
        if self._stderr_task and not self._stderr_task.done():
            try:
                await asyncio.wait_for(self._stderr_task, timeout=1.0)
            except Exception:
                self._stderr_task.cancel()

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()


@asynccontextmanager
async def with_machine(extra_args=None):
    machine = QTestMachine(extra_args=extra_args)
    try:
        await machine.start()
        yield machine
    finally:
        await machine.close()
