import re
import struct

import pytest

from framework.machine import with_machine
from helpers.images import build_nand_boot_image, build_sb_image


@pytest.mark.asyncio
async def test_nand_boot_contract(tmp_path):
    """NAND boot NCB/LDLB contract"""
    nand_path = tmp_path / "nand.bin"
    payload = struct.pack("<I", 0xDEADBEEF)
    sb_image = build_sb_image(
        payload,
        load_addr=0x00001000,
        jump_addr=0x00002000,
        jump_arg=0xCAFEBABE,
    )
    nand_image = build_nand_boot_image(sb_image)
    nand_path.write_bytes(nand_image)
    try:
        async with with_machine(
            [
                "-M", "stmp3770,boot-lcd-rs=1,boot-lcd-data=0xC",
                "-drive", f"if=none,format=raw,file={nand_path}",
            ]
        ) as machine:
            loaded = await machine.readl(0x00001000)
            assert loaded == 0xDEADBEEF, (
                f"NAND boot did not load SB payload: got 0x{loaded:x}"
            )
            assert re.search(
                r"NCB found in block 0",
                machine.stderr,
                re.IGNORECASE,
            ), f"NCB search not logged: {machine.stderr}"
            assert re.search(
                r"LDLB found in block 1",
                machine.stderr,
                re.IGNORECASE,
            ), f"LDLB search not logged: {machine.stderr}"
            assert re.search(
                r"STMP3770 SB: JUMP to 0x00002000",
                machine.stderr,
                re.IGNORECASE,
            ), f"SB JUMP not logged: {machine.stderr}"
    finally:
        nand_path.unlink(missing_ok=True)
