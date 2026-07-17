import pytest

from framework.constants import (
    DCP_BASE,
    ICOLL_BASE,
    DCP_PKT_INTERRUPT,
    DCP_PKT_DECR_SEMA,
    DCP_PKT_CHAIN,
    DCP_PKT_ENABLE_CIPHER,
    DCP_PKT_ENABLE_HASH,
    DCP_PKT_CIPHER_ENCRYPT,
    DCP_PKT_CIPHER_INIT,
    DCP_PKT_PAYLOAD_KEY,
    DCP_PKT_HASH_INIT,
    DCP_PKT_HASH_TERM,
    DCP_PKT_CHECK_HASH,
    DCP_PKT_ALL_SWAPS,
)
from helpers.dcp import (
    dcp_enable_channel0,
    dcp_write_descriptor,
    dcp_kick_channel0,
    dcp_kick,
)


@pytest.mark.asyncio
async def test_dcp_register_and_memcopy_contract(machine):
    """DCP register and memcopy contract"""
    assert (
        await machine.readl(DCP_BASE + 0x000)
    ) == 0xF0800000, "DCP CTRL must reset with SFTRST, CLKGATE, crypto, CSC, and gather capability bits"
    assert (
        await machine.readl(DCP_BASE + 0x010)
    ) == 0x10000000, "DCP STAT must report OTP_KEY_READY after reset"
    assert (
        await machine.readl(DCP_BASE + 0x020)
    ) == 0, "DCP CHANNELCTRL must reset disabled"
    assert (
        await machine.readl(DCP_BASE + 0x030)
    ) == 0x00000404, "DCP CAPABILITY0 must report four channels and four key slots"
    assert (
        await machine.readl(DCP_BASE + 0x040)
    ) == 0x00010001, "DCP CAPABILITY1 must report SHA1 and AES128 support"
    assert (
        await machine.readl(DCP_BASE + 0x420)
    ) == 0x01000000, "DCP VERSION must report v1.0"

    await machine.writel(DCP_BASE + 0x008, 0xC0800000)
    assert (
        await machine.readl(DCP_BASE + 0x000)
    ) == 0x30000000, "DCP CTRL_CLR must release reset and gate while preserving read-only present bits"
    await machine.writel(DCP_BASE + 0x004, 0x00E001FF)
    assert (
        await machine.readl(DCP_BASE + 0x000)
    ) == 0x30E001FF, "DCP CTRL_SET must retain only documented writable control bits"
    await machine.writel(DCP_BASE + 0x00C, 0xFFFFFFFF)
    assert (
        await machine.readl(DCP_BASE + 0x000)
    ) == 0xF0800000, "DCP CTRL_TOG must reset the block while preserving the documented reset contract"
    await machine.writel(DCP_BASE + 0x008, 0xC0000000)
    await machine.writel(DCP_BASE + 0x100, 0x00000100)
    assert (
        await machine.readl(DCP_BASE + 0x100)
    ) == 0x00000100, "DCP CH0CMDPTR must retain the descriptor address"
    await machine.writel(DCP_BASE + 0x110, 0x00000002)
    assert (
        await machine.readl(DCP_BASE + 0x110)
    ) == 0x00020000, "DCP CH0SEMA must expose its atomic count only in VALUE[23:16]"
    await machine.writel(DCP_BASE + 0x118, 0x000000FF)
    assert (
        await machine.readl(DCP_BASE + 0x110)
    ) == 0, "DCP CH0SEMA_CLR must clear the semaphore count"
    await machine.writel(DCP_BASE + 0x120, 0xFFFFFFFF)
    assert (
        await machine.readl(DCP_BASE + 0x120)
    ) == 0x00FF003E, "DCP CH0STAT must retain only its documented software-clearable error fields"
    await machine.writel(DCP_BASE + 0x128, 0x00FF003E)

    await machine.writel(DCP_BASE + 0x004, 0x00000001)
    await machine.writel(DCP_BASE + 0x024, 0x00000001)

    descriptor = 0x00000100
    source = 0x00000200
    destination = 0x00000300
    tag = 0x5A
    control = (tag << 24) | 0x00000013

    await machine.writel(source, 0x11223344)
    await machine.writel(source + 4, 0x55667788)
    await dcp_write_descriptor(
        machine,
        descriptor,
        ctrl0=control,
        source=source,
        destination=destination,
        size=8,
    )
    await dcp_kick_channel0(machine, descriptor, 1)

    assert (
        await machine.readl(destination)
    ) == 0x11223344, "DCP CH0 memcopy must transfer the first source word into SRAM"
    assert (
        await machine.readl(destination + 4)
    ) == 0x55667788, "DCP CH0 memcopy must transfer the complete requested buffer"
    assert (
        await machine.readl(descriptor + 0x1C)
    ) == 0x5A000001, "DCP must write the descriptor completion status with the command tag"
    assert (
        await machine.readl(DCP_BASE + 0x120)
    ) == 0x5A000000, "DCP CH0STAT must retain the completed command tag"
    assert (
        await machine.readl(DCP_BASE + 0x090)
    ) == control, "DCP PACKET1 must expose the active descriptor control snapshot"
    assert (
        await machine.readl(DCP_BASE + 0x0B0)
    ) == source, "DCP PACKET3 must expose the active descriptor source snapshot"
    assert (
        await machine.readl(DCP_BASE + 0x0C0)
    ) == destination, "DCP PACKET4 must expose the active descriptor destination snapshot"
    assert (
        (await machine.readl(DCP_BASE + 0x010)) & 1
    ) != 0, "DCP must latch CH0 interrupt status after an interrupting descriptor"
    assert (
        (await machine.readl(ICOLL_BASE + 0x050)) & (1 << 21)
    ) != 0, "DCP CH0 must assert the dedicated DCP VMI interrupt on ICOLL source 53"
    await machine.writel(DCP_BASE + 0x018, 1)
    assert (
        (await machine.readl(ICOLL_BASE + 0x050)) & (1 << 21)
    ) == 0, "DCP STAT_CLR must deassert the DCP VMI interrupt after acknowledgment"


@pytest.mark.asyncio
async def test_dcp_channel_register_map_contract(machine):
    """DCP channel register map contract"""
    for channel in [1, 2, 3]:
        base = DCP_BASE + 0x100 + channel * 0x40
        command = 0x01020304 * (channel + 1)

        await machine.writel(base + 0x00, command)
        assert (
            await machine.readl(base + 0x00)
        ) == command, f"DCP CH{channel}CMDPTR must retain its descriptor pointer"
        await machine.writel(base + 0x10, 2)
        assert (
            await machine.readl(base + 0x10)
        ) == 0x00020000, f"DCP CH{channel}SEMA must expose its count in VALUE[23:16] only"
        await machine.writel(base + 0x20, 0xFFFFFFFF)
        assert (
            await machine.readl(base + 0x20)
        ) == 0x00FF003E, f"DCP CH{channel}STAT must mask reserved bits"
        await machine.writel(base + 0x30, 0xFFFFFFFF)
        assert (
            await machine.readl(base + 0x30)
        ) == 0x0000FFFF, f"DCP CH{channel}OPTS must retain RECOVERY_TIMER only"


@pytest.mark.asyncio
async def test_dcp_key_and_context_register_contract(machine):
    """DCP key and context register contract"""
    await machine.writel(DCP_BASE + 0x050, 0x10203040)
    assert (
        await machine.readl(DCP_BASE + 0x050)
    ) == 0x10203040, "DCP CONTEXT must retain its complete pointer value"
    await machine.writel(DCP_BASE + 0x060, 0xFFFFFFFF)
    assert (
        await machine.readl(DCP_BASE + 0x060)
    ) == 0x00000033, "DCP KEY must retain only INDEX and SUBWORD fields"
    await machine.writel(DCP_BASE + 0x070, 0xA5A55A5A)
    assert (
        await machine.readl(DCP_BASE + 0x060)
    ) == 0x00000030, "DCP KEYDATA writes must advance KEY.SUBWORD with wraparound"
    await machine.writel(DCP_BASE + 0x060, 0x00000033)
    assert (
        await machine.readl(DCP_BASE + 0x070)
    ) == 0, "DCP KEYDATA must read as zero (key storage is write-only per PDF 15.2.2.1)"


@pytest.mark.asyncio
async def test_dcp_csc_register_map_contract(machine):
    """DCP CSC register map contract"""
    coefficient_resets = [
        [0x380, 0x012A8010],
        [0x390, 0x01980204],
        [0x3A0, 0x00D00064],
    ]
    coefficient_masks = [0x03FFFFFF, 0x03FF03FF, 0x03FF03FF]

    for offset, value in coefficient_resets:
        assert (
            await machine.readl(DCP_BASE + offset)
        ) == value, f"DCP CSC coefficient at 0x{offset:x} must have its documented reset"

    await machine.writel(DCP_BASE + 0x300, 0xFFFFFFFF)
    assert (
        await machine.readl(DCP_BASE + 0x300)
    ) == 0x00007FF1, "DCP CSCCTRL0 must mask all reserved control bits"
    await machine.writel(DCP_BASE + 0x310, 0xFFFFFFFF)
    assert (
        await machine.readl(DCP_BASE + 0x310)
    ) == 0x00FF0035, "DCP CSCSTAT must retain only documented status fields"
    await machine.writel(DCP_BASE + 0x320, 0xFFFFFFFF)
    assert (
        await machine.readl(DCP_BASE + 0x320)
    ) == 0x00FFFFFF, "DCP CSCOUTBUFPARAM must retain its 24 documented bits"
    await machine.writel(DCP_BASE + 0x330, 0xFFFFFFFF)
    assert (
        await machine.readl(DCP_BASE + 0x330)
    ) == 0x00000FFF, "DCP CSCINBUFPARAM must retain its 12 documented bits"

    for offset in [0x340, 0x350, 0x360, 0x370]:
        await machine.writel(DCP_BASE + offset, 0x10203040 + offset)
        assert (
            await machine.readl(DCP_BASE + offset)
        ) == 0x10203040 + offset, f"DCP CSC working pointer at 0x{offset:x} must be writable"

    for index, (offset, _reset) in enumerate(coefficient_resets):
        await machine.writel(DCP_BASE + offset, 0xFFFFFFFF)
        assert (
            await machine.readl(DCP_BASE + offset)
        ) == coefficient_masks[index], f"DCP CSC coefficient at 0x{offset:x} must hide reserved bits"

    for offset in [0x3E0, 0x3F0]:
        await machine.writel(DCP_BASE + offset, 0xFFFFFFFF)
        assert (
            await machine.readl(DCP_BASE + offset)
        ) == 0x03FFFFFF, f"DCP CSC scale at 0x{offset:x} must retain documented bits"

    await machine.writel(DCP_BASE + 0x400, 0xFFFFFFFF)
    assert (
        await machine.readl(DCP_BASE + 0x400)
    ) == 0x000000FF, "DCP DBGSELECT must retain only its byte-wide selector"
    await machine.writel(DCP_BASE + 0x410, 0xFFFFFFFF)
    assert (
        await machine.readl(DCP_BASE + 0x410)
    ) == 0, "DCP DBGDATA must remain read-only"


@pytest.mark.asyncio
async def test_dcp_sct_alias_contract(machine):
    """DCP SCT alias contract"""
    # Reset DCP to known state.
    await machine.writel(DCP_BASE + 0x004, 0xC0800000)
    await machine.writel(DCP_BASE + 0x008, 0xC0800000)

    # CSCSTAT (0x310) has SET only per PDF Table 649.
    # CLR (0x318) and TOG (0x31c) must be rejected.
    await machine.writel(DCP_BASE + 0x310, 0x00FF0035)
    assert (
        await machine.readl(DCP_BASE + 0x310)
    ) == 0x00FF0035, "DCP CSCSTAT direct write must populate documented fields"
    await machine.writel(DCP_BASE + 0x318, 0x00FF0035)
    assert (
        await machine.readl(DCP_BASE + 0x310)
    ) == 0x00FF0035, "DCP CSCSTAT_CLR must be rejected (undocumented alias)"
    await machine.writel(DCP_BASE + 0x31C, 0x00FF0035)
    assert (
        await machine.readl(DCP_BASE + 0x310)
    ) == 0x00FF0035, "DCP CSCSTAT_TOG must be rejected (undocumented alias)"
    # SET alias must work.
    await machine.writel(DCP_BASE + 0x310, 0x00000000)
    await machine.writel(DCP_BASE + 0x314, 0x00000001)
    assert (
        await machine.readl(DCP_BASE + 0x310)
    ) == 0x00000001, "DCP CSCSTAT_SET must set the COMPLETE bit"

    # CH0 STAT (0x120) has SET + CLR but no TOG per PDF Table 649.
    # CH0 OPTS (0x130) has SET + CLR but no TOG.
    await machine.writel(DCP_BASE + 0x120, 0x00FF003E)
    await machine.writel(DCP_BASE + 0x12C, 0x00FF003E)
    assert (
        await machine.readl(DCP_BASE + 0x120)
    ) == 0x00FF003E, "DCP CH0STAT_TOG must be rejected (undocumented alias)"
    await machine.writel(DCP_BASE + 0x130, 0x0000FFFF)
    await machine.writel(DCP_BASE + 0x13C, 0x0000FFFF)
    assert (
        await machine.readl(DCP_BASE + 0x130)
    ) == 0x0000FFFF, "DCP CH0OPTS_TOG must be rejected (undocumented alias)"

    # CH1 STAT (0x160) has SET + CLR but no TOG.
    # CH1 OPTS (0x170) has SET + CLR + TOG (TOG is documented).
    await machine.writel(DCP_BASE + 0x160, 0x00FF003E)
    await machine.writel(DCP_BASE + 0x16C, 0x00FF003E)
    assert (
        await machine.readl(DCP_BASE + 0x160)
    ) == 0x00FF003E, "DCP CH1STAT_TOG must be rejected (undocumented alias)"
    await machine.writel(DCP_BASE + 0x170, 0x0000AAAA)
    await machine.writel(DCP_BASE + 0x17C, 0x0000FFFF)
    assert (
        await machine.readl(DCP_BASE + 0x170)
    ) == 0x00005555, "DCP CH1OPTS_TOG must toggle documented bits"

    # CH2/CH3 STAT and OPTS have full SET + CLR + TOG.
    await machine.writel(DCP_BASE + 0x1A0, 0x00FF003E)
    await machine.writel(DCP_BASE + 0x1AC, 0x0000003E)
    assert (
        await machine.readl(DCP_BASE + 0x1A0)
    ) == 0x00FF0000, "DCP CH2STAT_TOG must toggle documented error bits"


@pytest.mark.asyncio
async def test_dcp_aes128_ecb_contract(machine):
    """DCP AES-128 ECB contract"""
    await dcp_enable_channel0(machine)

    # FIPS-197 Appendix B vector via payload key in natural byte order.
    payload = 0x00000600
    source = 0x00000700
    destination = 0x00000800
    descriptor = 0x00000100
    for i, word in enumerate([0x03020100, 0x07060504, 0x0B0A0908, 0x0F0E0D0C]):
        await machine.writel(payload + 4 * i, word)
    for i, word in enumerate([0x33221100, 0x77665544, 0xBBAA9988, 0xFFEEDDCC]):
        await machine.writel(source + 4 * i, word)

    await dcp_write_descriptor(
        machine,
        descriptor,
        ctrl0=(0x25 << 24)
        | DCP_PKT_ALL_SWAPS
        | DCP_PKT_PAYLOAD_KEY
        | DCP_PKT_CIPHER_ENCRYPT
        | DCP_PKT_ENABLE_CIPHER
        | DCP_PKT_DECR_SEMA
        | DCP_PKT_INTERRUPT,
        source=source,
        destination=destination,
        size=16,
        payload=payload,
    )
    await dcp_kick_channel0(machine, descriptor, 1)

    actual = [
        await machine.readl(destination),
        await machine.readl(destination + 4),
        await machine.readl(destination + 8),
        await machine.readl(destination + 12),
    ]
    expected = [0xD8E0C469, 0x30047B6A, 0x80B7CDD8, 0x5AC5B470]
    assert actual == expected, "DCP AES-128 ECB encrypt must reproduce the FIPS-197 known answer"
    assert (
        await machine.readl(descriptor + 0x1C)
    ) == 0x25000001, "DCP AES descriptor must complete with its command tag"
    assert (
        await machine.readl(DCP_BASE + 0x110)
    ) == 0, "DCP AES descriptor must consume the channel semaphore"

    # Same vector via the KEYDATA key storage, no swaps (PDF key order).
    await machine.writel(DCP_BASE + 0x060, 0)
    for word in [0x0C0D0E0F, 0x08090A0B, 0x04050607, 0x00010203]:
        await machine.writel(DCP_BASE + 0x070, word)
    assert (
        await machine.readl(DCP_BASE + 0x070)
    ) == 0, "DCP KEYDATA must read back as zero after key programming (write-only)"

    source2 = 0x00000900
    destination2 = 0x00000A00
    descriptor2 = 0x00000140
    for i, word in enumerate([0xCCDDEEFF, 0x8899AABB, 0x44556677, 0x00112233]):
        await machine.writel(source2 + 4 * i, word)

    await dcp_write_descriptor(
        machine,
        descriptor2,
        ctrl0=(0x5A << 24)
        | DCP_PKT_CIPHER_ENCRYPT
        | DCP_PKT_ENABLE_CIPHER
        | DCP_PKT_DECR_SEMA
        | DCP_PKT_INTERRUPT,
        source=source2,
        destination=destination2,
        size=16,
    )
    await dcp_kick_channel0(machine, descriptor2, 1)

    actual2 = [
        await machine.readl(destination2),
        await machine.readl(destination2 + 4),
        await machine.readl(destination2 + 8),
        await machine.readl(destination2 + 12),
    ]
    expected2 = [0x70B4C55A, 0xD8CDB780, 0x6A7B0430, 0x69C4E0D8]
    assert (
        actual2 == expected2
    ), "DCP AES-128 ECB with the key RAM and no swaps must use the PDF key word order"


@pytest.mark.asyncio
async def test_dcp_aes128_cbc_contract(machine):
    """DCP AES-128 CBC contract"""
    await dcp_enable_channel0(machine)

    # Key 000102...0f, IV a0a1...af, plaintext 0001...1f (natural order).
    payload = 0x00000600
    source = 0x00000700
    destination = 0x00000800
    descriptor = 0x00000100
    for i, word in enumerate([0x03020100, 0x07060504, 0x0B0A0908, 0x0F0E0D0C]):
        await machine.writel(payload + 4 * i, word)
    for i, word in enumerate([0xA3A2A1A0, 0xA7A6A5A4, 0xABAAA9A8, 0xAFAEADAC]):
        await machine.writel(payload + 16 + 4 * i, word)

    plain_words = [
        0x03020100,
        0x07060504,
        0x0B0A0908,
        0x0F0E0D0C,
        0x13121110,
        0x17161514,
        0x1B1A1918,
        0x1F1E1D1C,
    ]
    for i, word in enumerate(plain_words):
        await machine.writel(source + 4 * i, word)

    await dcp_write_descriptor(
        machine,
        descriptor,
        ctrl0=(0x11 << 24)
        | DCP_PKT_ALL_SWAPS
        | DCP_PKT_PAYLOAD_KEY
        | DCP_PKT_CIPHER_INIT
        | DCP_PKT_CIPHER_ENCRYPT
        | DCP_PKT_ENABLE_CIPHER
        | DCP_PKT_DECR_SEMA
        | DCP_PKT_INTERRUPT,
        ctrl1=0x00000010,
        source=source,
        destination=destination,
        size=32,
        payload=payload,
    )
    await dcp_kick_channel0(machine, descriptor, 1)

    cipher_words = [
        0xB6A8F1FE,
        0x3AC4F025,
        0x23B60871,
        0xCA90FBA6,
        0x8993BE81,
        0x4AFA167D,
        0x81F347A3,
        0x6A7769E1,
    ]
    for i, word in enumerate(cipher_words):
        assert (
            await machine.readl(destination + 4 * i)
        ) == word, f"DCP AES-128 CBC encrypt word {i} must match the known answer"

    # Decrypt the ciphertext back with the same key and IV.
    destination2 = 0x00000900
    descriptor2 = 0x00000140
    await dcp_write_descriptor(
        machine,
        descriptor2,
        ctrl0=(0x22 << 24)
        | DCP_PKT_ALL_SWAPS
        | DCP_PKT_PAYLOAD_KEY
        | DCP_PKT_CIPHER_INIT
        | DCP_PKT_ENABLE_CIPHER
        | DCP_PKT_DECR_SEMA
        | DCP_PKT_INTERRUPT,
        ctrl1=0x00000010,
        source=destination,
        destination=destination2,
        size=32,
        payload=payload,
    )
    await dcp_kick_channel0(machine, descriptor2, 1)
    for i, word in enumerate(plain_words):
        assert (
            await machine.readl(destination2 + 4 * i)
        ) == word, f"DCP AES-128 CBC decrypt round-trip word {i} must restore the plaintext"


@pytest.mark.asyncio
async def test_dcp_sha1_contract(machine):
    """DCP SHA-1 contract"""
    await dcp_enable_channel0(machine)

    # Single-packet SHA-1 of "abc" (FIPS 180-1 A.1 vector).
    source = 0x00000700
    payload = 0x00000780
    descriptor = 0x00000100
    await machine.writel(source, 0x00636261)
    await dcp_write_descriptor(
        machine,
        descriptor,
        ctrl0=(0x33 << 24)
        | DCP_PKT_HASH_INIT
        | DCP_PKT_HASH_TERM
        | DCP_PKT_ENABLE_HASH
        | DCP_PKT_DECR_SEMA
        | DCP_PKT_INTERRUPT,
        source=source,
        size=3,
        payload=payload,
    )
    await dcp_kick_channel0(machine, descriptor, 1)

    actual = [
        await machine.readl(payload),
        await machine.readl(payload + 4),
        await machine.readl(payload + 8),
        await machine.readl(payload + 12),
        await machine.readl(payload + 16),
    ]
    expected = [0xA9993E36, 0x4706816A, 0xBA3E2571, 0x7850C26C, 0x9CD0D89D]
    assert actual == expected, 'DCP SHA-1 must hash "abc" to the FIPS 180-1 known answer'

    # Chained two-packet hash of 'a' * 64 + "abc" (init, then terminate).
    source2 = 0x00000800
    payload2 = 0x00000880
    descriptor2 = 0x00000180
    descriptor3 = 0x000001C0
    for i in range(16):
        await machine.writel(source2 + 4 * i, 0x61616161)
    await machine.writel(source2 + 0x40, 0x00636261)

    await dcp_write_descriptor(
        machine,
        descriptor2,
        nxt=descriptor3,
        ctrl0=(0x44 << 24)
        | DCP_PKT_HASH_INIT
        | DCP_PKT_ENABLE_HASH
        | DCP_PKT_CHAIN
        | DCP_PKT_DECR_SEMA,
        source=source2,
        size=64,
    )
    await dcp_write_descriptor(
        machine,
        descriptor3,
        ctrl0=(0x55 << 24)
        | DCP_PKT_HASH_TERM
        | DCP_PKT_ENABLE_HASH
        | DCP_PKT_DECR_SEMA
        | DCP_PKT_INTERRUPT,
        source=source2 + 0x40,
        size=3,
        payload=payload2,
    )
    await dcp_kick_channel0(machine, descriptor2, 2)
    assert (
        await machine.readl(descriptor2 + 0x1C)
    ) == 0x44000001, "DCP chained hash init descriptor must complete first"
    await machine.writel(DCP_BASE + 0x110, 0)
    assert (
        await machine.readl(descriptor3 + 0x1C)
    ) == 0x55000001, "DCP chained hash terminate descriptor must complete after re-kick"

    actual2 = [
        await machine.readl(payload2),
        await machine.readl(payload2 + 4),
        await machine.readl(payload2 + 8),
        await machine.readl(payload2 + 12),
        await machine.readl(payload2 + 16),
    ]
    expected2 = [0xA5177E48, 0xD19A714D, 0x0463DBEA, 0xFAAB7F5C, 0x6D140FF3]
    assert (
        actual2 == expected2
    ), "DCP SHA-1 must continue hashing across chained descriptors"


@pytest.mark.asyncio
async def test_dcp_crc32_contract(machine):
    """DCP CRC-32 contract"""
    await dcp_enable_channel0(machine)

    # DCP CRC-32: init 0xffffffff, zero-padded to words, no final xor.
    source = 0x00000700
    payload = 0x00000780
    descriptor = 0x00000100
    await machine.writel(source, 0x00636261)
    await dcp_write_descriptor(
        machine,
        descriptor,
        ctrl0=(0x66 << 24)
        | DCP_PKT_HASH_INIT
        | DCP_PKT_HASH_TERM
        | DCP_PKT_ENABLE_HASH
        | DCP_PKT_DECR_SEMA
        | DCP_PKT_INTERRUPT,
        ctrl1=0x00010000,
        source=source,
        size=3,
        payload=payload,
    )
    await dcp_kick_channel0(machine, descriptor, 1)
    assert (
        await machine.readl(payload)
    ) == 0x58A297AF, 'DCP CRC-32 of "abc" must use the PDF modified CRC-32 contract'

    # Non-word-aligned 9-byte buffer exercises the zero padding.
    source2 = 0x00000800
    payload2 = 0x00000880
    descriptor2 = 0x00000140
    await machine.writel(source2, 0x34333231)
    await machine.writel(source2 + 4, 0x38373635)
    await machine.writel(source2 + 8, 0x00000039)
    await dcp_write_descriptor(
        machine,
        descriptor2,
        ctrl0=(0x77 << 24)
        | DCP_PKT_HASH_INIT
        | DCP_PKT_HASH_TERM
        | DCP_PKT_ENABLE_HASH
        | DCP_PKT_DECR_SEMA
        | DCP_PKT_INTERRUPT,
        ctrl1=0x00010000,
        source=source2,
        size=9,
        payload=payload2,
    )
    await dcp_kick_channel0(machine, descriptor2, 1)
    assert (
        await machine.readl(payload2)
    ) == 0x882AA7CB, 'DCP CRC-32 of "123456789" must pad trailing bytes with zeros'


@pytest.mark.asyncio
async def test_dcp_hash_check_contract(machine):
    """DCP hash check contract"""
    await dcp_enable_channel0(machine)

    # Matching CHECK_HASH payload completes without HASH_MISMATCH.
    source = 0x00000700
    payload = 0x00000780
    descriptor = 0x00000100
    await machine.writel(source, 0x00636261)
    for i, word in enumerate([0xA9993E36, 0x4706816A, 0xBA3E2571, 0x7850C26C, 0x9CD0D89D]):
        await machine.writel(payload + 4 * i, word)
    await dcp_write_descriptor(
        machine,
        descriptor,
        ctrl0=(0x48 << 24)
        | DCP_PKT_CHECK_HASH
        | DCP_PKT_HASH_INIT
        | DCP_PKT_HASH_TERM
        | DCP_PKT_ENABLE_HASH
        | DCP_PKT_DECR_SEMA
        | DCP_PKT_INTERRUPT,
        source=source,
        size=3,
        payload=payload,
    )
    await dcp_kick_channel0(machine, descriptor, 1)
    assert (
        await machine.readl(descriptor + 0x1C)
    ) == 0x48000001, "DCP CHECK_HASH with a matching digest must complete normally"
    assert (
        (await machine.readl(DCP_BASE + 0x120)) & 2
    ) == 0, "DCP CHECK_HASH match must not raise HASH_MISMATCH"

    # Mismatched digest interrupts and terminates the chain.
    descriptor2 = 0x00000140
    await machine.writel(payload, 0xA9993E37)
    await machine.writel(DCP_BASE + 0x018, 1)
    await machine.writel(DCP_BASE + 0x128, 0x00FF003E)
    await dcp_write_descriptor(
        machine,
        descriptor2,
        ctrl0=(0x59 << 24)
        | DCP_PKT_CHECK_HASH
        | DCP_PKT_HASH_INIT
        | DCP_PKT_HASH_TERM
        | DCP_PKT_ENABLE_HASH
        | DCP_PKT_DECR_SEMA,
        source=source,
        size=3,
        payload=payload,
    )
    await dcp_kick_channel0(machine, descriptor2, 1)
    assert (
        (await machine.readl(DCP_BASE + 0x120)) & 2
    ) != 0, "DCP CHECK_HASH mismatch must raise CH0STAT.HASH_MISMATCH"
    assert (
        (await machine.readl(DCP_BASE + 0x010)) & 1
    ) != 0, "DCP CHECK_HASH mismatch must latch the channel interrupt status"
    assert (
        await machine.readl(DCP_BASE + 0x110)
    ) == 0, "DCP CHECK_HASH mismatch must terminate the channel chain"


@pytest.mark.asyncio
async def test_dcp_multi_channel_contract(machine):
    """DCP multi-channel contract"""
    # Enable channels 0-3, CH1 at high priority, IRQ enables for all.
    await machine.writel(DCP_BASE + 0x008, 0xC0000000)
    await machine.writel(DCP_BASE + 0x024, 0x0000020F)
    await machine.writel(DCP_BASE + 0x004, 0x0000000F)

    # CH1 high-priority AES-128 ECB packet and CH0 low-priority memcopy.
    payload = 0x00000600
    source = 0x00000700
    destination = 0x00000800
    descriptor = 0x00000100
    for i, word in enumerate([0x03020100, 0x07060504, 0x0B0A0908, 0x0F0E0D0C]):
        await machine.writel(payload + 4 * i, word)
    for i, word in enumerate([0x33221100, 0x77665544, 0xBBAA9988, 0xFFEEDDCC]):
        await machine.writel(source + 4 * i, word)

    await dcp_write_descriptor(
        machine,
        descriptor,
        ctrl0=(0x31 << 24)
        | DCP_PKT_ALL_SWAPS
        | DCP_PKT_PAYLOAD_KEY
        | DCP_PKT_CIPHER_ENCRYPT
        | DCP_PKT_ENABLE_CIPHER
        | DCP_PKT_DECR_SEMA
        | DCP_PKT_INTERRUPT,
        source=source,
        destination=destination,
        size=16,
        payload=payload,
    )

    descriptor0 = 0x00000140
    await dcp_write_descriptor(
        machine,
        descriptor0,
        ctrl0=(0x30 << 24) | 0x00000013,
        source=source,
        destination=destination + 0x100,
        size=16,
    )

    await machine.writel(DCP_BASE + 0x100, descriptor0)
    await dcp_kick(machine, 1, descriptor, 1)
    await machine.writel(DCP_BASE + 0x110, 1)

    assert (
        await machine.readl(destination)
    ) == 0xD8E0C469, "DCP CH1 must execute AES-128 ECB through the shared engine"
    assert (
        await machine.readl(descriptor + 0x1C)
    ) == 0x31000001, "DCP CH1 descriptor must complete with its command tag"
    assert (
        await machine.readl(destination + 0x100)
    ) == 0x33221100, "DCP CH0 must complete its memcopy after the high-priority channel"
    assert (
        await machine.readl(descriptor0 + 0x1C)
    ) == 0x30000001, "DCP CH0 descriptor must complete through arbitration"
    assert (
        (await machine.readl(DCP_BASE + 0x010)) & 3
    ) == 3, "DCP STAT must latch interrupt status for both serviced channels"
    assert (
        (await machine.readl(DCP_BASE + 0x010)) & 0x0FFF0000
    ) == 0, "DCP STAT READY/CUR_CHANNEL must be idle once arbitration drains"
    await machine.writel(DCP_BASE + 0x018, 0x00000003)

    # CH2 memcopy and CH3 SHA-1 through their own register files.
    descriptor2 = 0x00000180
    descriptor3 = 0x000001C0
    payload3 = 0x00000580
    await dcp_write_descriptor(
        machine,
        descriptor2,
        ctrl0=(0x32 << 24) | 0x00000013,
        source=source,
        destination=destination + 0x200,
        size=8,
    )
    await dcp_write_descriptor(
        machine,
        descriptor3,
        ctrl0=(0x33 << 24)
        | DCP_PKT_HASH_INIT
        | DCP_PKT_HASH_TERM
        | DCP_PKT_ENABLE_HASH
        | DCP_PKT_DECR_SEMA
        | DCP_PKT_INTERRUPT,
        source=source + 0x40,
        size=3,
        payload=payload3,
    )
    await machine.writel(source + 0x40, 0x00636261)
    await dcp_kick(machine, 2, descriptor2, 1)
    await dcp_kick(machine, 3, descriptor3, 1)

    assert (
        await machine.readl(destination + 0x200)
    ) == 0x33221100, "DCP CH2 must execute its memcopy descriptor"
    assert (
        await machine.readl(payload3)
    ) == 0xA9993E36, "DCP CH3 must execute SHA-1 through the shared engine"
    assert (
        (await machine.readl(DCP_BASE + 0x010)) & 0x0C
    ) == 0x0C, "DCP STAT must latch interrupt status for CH2 and CH3"
    assert (
        (await machine.readl(ICOLL_BASE + 0x050)) & (1 << 22)
    ) != 0, "DCP CH1-3 interrupts must assert the shared DCP IRQ on ICOLL source 54"


@pytest.mark.asyncio
async def test_dcp_channel_error_recovery_contract(machine):
    """DCP channel error recovery contract"""
    await machine.writel(DCP_BASE + 0x008, 0xC0000000)
    await machine.writel(DCP_BASE + 0x024, 0x00000006)
    await machine.writel(DCP_BASE + 0x004, 0x00000006)

    # CH1 descriptor fetch from an unmapped address stalls the channel.
    await dcp_kick(machine, 1, 0x50000000, 1)
    assert (
        (await machine.readl(DCP_BASE + 0x160)) & 0x3E
    ) == 0x08, "DCP CH1STAT must raise ERROR_PACKET on a bus faulting descriptor"
    assert (
        await machine.readl(DCP_BASE + 0x150)
    ) == 0x00010000, "DCP stalled channel must preserve its semaphore for recovery"
    assert (
        (await machine.readl(DCP_BASE + 0x010)) & 2
    ) == 2, "DCP STAT must latch the faulting channel interrupt status"

    # Software repairs the pointer, clears the error, and the channel runs.
    source = 0x00000700
    destination = 0x00000800
    descriptor = 0x00000100
    await machine.writel(source, 0xCAFEBABE)
    await machine.writel(source + 4, 0xDEADBEEF)
    await dcp_write_descriptor(
        machine,
        descriptor,
        ctrl0=(0x41 << 24) | 0x00000013,
        source=source,
        destination=destination,
        size=8,
    )
    await machine.writel(DCP_BASE + 0x140, descriptor)
    await machine.writel(DCP_BASE + 0x168, 0x00FF003E)
    assert (
        await machine.readl(destination)
    ) == 0xCAFEBABE, "DCP channel must resume its descriptor after software error recovery"
    assert (
        await machine.readl(descriptor + 0x1C)
    ) == 0x41000001, "DCP recovered descriptor must complete with its command tag"
    assert (
        await machine.readl(DCP_BASE + 0x150)
    ) == 0, "DCP recovered channel must consume the preserved semaphore"

    # Semaphore nonzero without a chain bit raises the NO_CHAIN error.
    descriptor2 = 0x00000140
    await dcp_write_descriptor(
        machine,
        descriptor2,
        ctrl0=(0x42 << 24) | 0x00000013,
        source=source,
        destination=destination + 0x100,
        size=8,
    )
    await dcp_kick(machine, 2, descriptor2, 2)
    assert (
        await machine.readl(DCP_BASE + 0x1A0)
    ) == 0x42020008, "DCP must raise ERROR_PACKET/NO_CHAIN when the semaphore outlives the chain"


@pytest.mark.asyncio
async def test_dcp_context_switch_contract(machine):
    """DCP context switch contract"""
    await machine.writel(DCP_BASE + 0x008, 0xC0000000)
    await machine.writel(DCP_BASE + 0x024, 0x00000003)
    await machine.writel(DCP_BASE + 0x004, 0x00000003)
    await machine.writel(DCP_BASE + 0x004, 0x00200000)
    await machine.writel(DCP_BASE + 0x050, 0x00000600)

    # CH0 starts a SHA-1 pass; its context must land in the context buffer.
    source = 0x00000700
    descriptor = 0x00000100
    for i in range(16):
        await machine.writel(source + 4 * i, 0x61616161)
    await dcp_write_descriptor(
        machine,
        descriptor,
        ctrl0=(0x51 << 24)
        | DCP_PKT_HASH_INIT
        | DCP_PKT_ENABLE_HASH
        | DCP_PKT_DECR_SEMA,
        source=source,
        size=64,
    )
    await dcp_kick_channel0(machine, descriptor, 1)

    actual = [
        await machine.readl(0x688),
        await machine.readl(0x68C),
        await machine.readl(0x690),
        await machine.readl(0x694),
        await machine.readl(0x698),
        await machine.readl(0x69C),
    ]
    expected = [0xDA4968EB, 0x2E377C1F, 0x884E8F52, 0x83524BEB, 0xE74EBDBD, 512]
    assert (
        actual == expected
    ), "DCP must save the CH0 SHA-1 context to the context buffer on completion"

    # CH1 memcopy switches the engine away from CH0.
    descriptor1 = 0x00000140
    await dcp_write_descriptor(
        machine,
        descriptor1,
        ctrl0=(0x52 << 24) | 0x00000013,
        source=source,
        destination=0x00000800,
        size=8,
    )
    await dcp_kick(machine, 1, descriptor1, 1)

    # CH0 resumes the hash; the context must be reloaded from the buffer.
    payload = 0x00000580
    descriptor2 = 0x00000180
    await machine.writel(source + 0x40, 0x00636261)
    await dcp_write_descriptor(
        machine,
        descriptor2,
        ctrl0=(0x53 << 24)
        | DCP_PKT_HASH_TERM
        | DCP_PKT_ENABLE_HASH
        | DCP_PKT_DECR_SEMA
        | DCP_PKT_INTERRUPT,
        source=source + 0x40,
        size=3,
        payload=payload,
    )
    await dcp_kick_channel0(machine, descriptor2, 1)

    actual2 = [
        await machine.readl(payload),
        await machine.readl(payload + 4),
        await machine.readl(payload + 8),
        await machine.readl(payload + 12),
        await machine.readl(payload + 16),
    ]
    expected2 = [0xA5177E48, 0xD19A714D, 0x0463DBEA, 0xFAAB7F5C, 0x6D140FF3]
    assert (
        actual2 == expected2
    ), "DCP must continue the CH0 hash from the saved context after a channel switch"


@pytest.mark.asyncio
async def test_dcp_csc_contract(machine):
    """DCP CSC contract"""
    await machine.writel(DCP_BASE + 0x008, 0xC0000000)
    await machine.writel(DCP_BASE + 0x004, 0x00000100)

    # 2x2 YUV420 frame, planar luma and chroma.
    luma = 0x00001000
    chromau = 0x00001010
    chromav = 0x00001014
    rgb = 0x00002000
    for i, byte in enumerate([255, 0, 128, 76]):
        await machine.writeb(luma + i, byte)
    await machine.writeb(chromau, 150)
    await machine.writeb(chromav, 40)

    await machine.writel(DCP_BASE + 0x320, (2 << 12) | 2)
    await machine.writel(DCP_BASE + 0x330, 2)
    await machine.writel(DCP_BASE + 0x340, rgb)
    await machine.writel(DCP_BASE + 0x350, luma)
    await machine.writel(DCP_BASE + 0x360, chromau)
    await machine.writel(DCP_BASE + 0x370, chromav)
    await machine.writel(DCP_BASE + 0x300, 0x00000201)

    actual = [
        await machine.readl(rgb),
        await machine.readl(rgb + 4),
        await machine.readl(rgb + 8),
        await machine.readl(rgb + 12),
    ]
    expected = [0xFFFF8A00, 0x1A2C0000, 0xAFC10000, 0x72850000]
    assert actual == expected, "DCP CSC must convert the YUV420 frame to RGB24 with the reset coefficients"
    assert (
        (await machine.readl(DCP_BASE + 0x310)) & 1
    ) == 1, "DCP CSCSTAT must report completion"
    assert (
        (await machine.readl(DCP_BASE + 0x300)) & 1
    ) == 1, "DCP CSC ENABLE must remain latched for software after completion"
    assert (
        (await machine.readl(DCP_BASE + 0x010)) & 0x100
    ) == 0x100, "DCP STAT must latch the CSC interrupt"
    assert (
        await machine.readl(DCP_BASE + 0x350)
    ) == luma + 4, "DCP CSC luma pointer must advance past the consumed input"
    assert (
        await machine.readl(DCP_BASE + 0x340)
    ) == rgb + 16, "DCP CSC RGB pointer must advance past the written output"

    # Same frame converted to RGB16_565.
    rgb565 = 0x00002100
    await machine.writel(DCP_BASE + 0x310, 0)
    await machine.writel(DCP_BASE + 0x300, 0)
    await machine.writel(DCP_BASE + 0x340, rgb565)
    await machine.writel(DCP_BASE + 0x350, luma)
    await machine.writel(DCP_BASE + 0x360, chromau)
    await machine.writel(DCP_BASE + 0x370, chromav)
    await machine.writel(DCP_BASE + 0x300, 0x00000001)

    actual2 = [await machine.readl(rgb565), await machine.readl(rgb565 + 4)]
    expected2 = [0x01638FFF, 0x042E0615]
    assert actual2 == expected2, "DCP CSC must convert the same frame to RGB16_565"
