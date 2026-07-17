import re
import struct

import pytest

from framework.machine import with_machine
from helpers.images import build_existos_sb_image, build_sb_fill_image, build_sb_image


@pytest.mark.asyncio
async def test_sb_image_load_and_jump(tmp_path):
    """SB image LOAD and JUMP contract"""
    sb_path = tmp_path / "test.sb"
    payload = struct.pack("<I", 0xDEADBEEF)
    image = build_sb_image(
        payload,
        load_addr=0x00001000,
        jump_addr=0x00002000,
        jump_arg=0xCAFEBABE,
    )
    sb_path.write_bytes(image)
    try:
        async with with_machine(["-M", f"stmp3770,sb-image={sb_path}"]) as machine:
            loaded = await machine.readl(0x00001000)
            assert loaded == 0xDEADBEEF, (
                f"SB LOAD did not write payload: got 0x{loaded:x}"
            )
            assert re.search(
                r"STMP3770 SB: JUMP to 0x00002000",
                machine.stderr,
                re.IGNORECASE,
            ), f"SB JUMP not logged in stderr: {machine.stderr}"
            assert re.search(
                r"r0=0xcafebabe",
                machine.stderr,
                re.IGNORECASE,
            ), f"SB JUMP r0 arg not logged: {machine.stderr}"
    finally:
        sb_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_sb_image_fill_command(tmp_path):
    """SB image FILL command contract"""
    sb_path = tmp_path / "sb_fill.sb"
    fill_addr = 0x00003000
    fill_count = 16
    fill_pattern = 0xAABBCCDD
    image = build_sb_fill_image(fill_addr, fill_count, fill_pattern)
    sb_path.write_bytes(image)
    try:
        async with with_machine(["-M", f"stmp3770,sb-image={sb_path}"]) as machine:
            for i in range(0, fill_count, 4):
                val = await machine.readl(fill_addr + i)
                assert val == fill_pattern, (
                    f"SB FILL pattern mismatch at 0x{(fill_addr + i):x}: "
                    f"got 0x{val:x}, expected 0x{fill_pattern:x}"
                )
    finally:
        sb_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_sb_image_exist_os_format(tmp_path):
    """SB image ExistOS format contract"""
    sb_path = tmp_path / "sb_existos.sb"
    payload = struct.pack("<I", 0xDEADBEEF)
    image = build_existos_sb_image(
        payload,
        load_addr=0x00001000,
        jump_addr=0x00002000,
        jump_arg=0xCAFEBABE,
    )
    sb_path.write_bytes(image)
    try:
        async with with_machine(["-M", f"stmp3770,sb-image={sb_path}"]) as machine:
            loaded = await machine.readl(0x00001000)
            assert loaded == 0xDEADBEEF, (
                f"ExistOS SB LOAD did not write payload: got 0x{loaded:x}"
            )
            assert re.search(
                r"STMP3770 SB: JUMP to 0x00002000",
                machine.stderr,
                re.IGNORECASE,
            ), f"ExistOS SB JUMP not logged: {machine.stderr}"
            assert re.search(
                r"r0=0xcafebabe",
                machine.stderr,
                re.IGNORECASE,
            ), f"ExistOS SB JUMP r0 arg not logged: {machine.stderr}"
    finally:
        sb_path.unlink(missing_ok=True)
