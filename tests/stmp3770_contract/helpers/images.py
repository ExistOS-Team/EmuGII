import math
import struct

from helpers.crypto import aes_cbc_encrypt, crc32, random_bytes, sha1

SB_BLOCK_SIZE = 16


def _write_u32le(buf: bytearray, offset: int, value: int):
    struct.pack_into("<I", buf, offset, value & 0xFFFFFFFF)


def _write_u16le(buf: bytearray, offset: int, value: int):
    struct.pack_into("<H", buf, offset, value & 0xFFFF)


def _write_bytes(buf: bytearray, offset: int, data: bytes):
    buf[offset:offset + len(data)] = data


def _pad_to_block(data: bytes) -> bytearray:
    blocks = math.ceil(len(data) / SB_BLOCK_SIZE)
    padded = bytearray(blocks * SB_BLOCK_SIZE)
    padded[:len(data)] = data
    return padded


def _build_plain_header(*, first_boot_tag_block, image_blocks, key_count=0, key_dictionary_block=0):
    header = bytearray(96)
    _write_bytes(header, 20, b"STMP")
    header[24] = 1
    header[25] = 1
    _write_u16le(header, 26, 0)
    _write_u32le(header, 28, image_blocks)
    _write_u32le(header, 32, first_boot_tag_block)
    _write_u32le(header, 36, 0)  # first_boot_section_id
    _write_u16le(header, 40, key_count)
    _write_u16le(header, 42, key_dictionary_block)
    _write_u16le(header, 44, 6)  # header_blocks
    _write_u16le(header, 46, 1)  # section_count
    _write_u16le(header, 48, 1)  # section_header_size
    _write_bytes(header, 52, b"sgtl")
    _write_u16le(header, 64, 1)
    _write_u16le(header, 76, 1)
    return header


def build_sb_image(payload: bytes, load_addr: int, jump_addr: int, jump_arg: int = 0):
    """Build a minimal SB v1.1 image (LOAD + JUMP) encrypted with the zero key."""
    key = bytes(16)
    iv = bytes(16)

    payload_blocks = math.ceil(len(payload) / SB_BLOCK_SIZE)
    section_size = 1 + payload_blocks + 1  # TAG + LOAD data + JUMP
    header_blocks = 6
    sect_hdr_blocks = 1
    first_boot_tag_block = header_blocks + sect_hdr_blocks
    total_blocks = first_boot_tag_block + 1 + section_size

    header = _build_plain_header(
        first_boot_tag_block=first_boot_tag_block,
        image_blocks=total_blocks,
    )

    sect_hdr = bytearray(16)
    _write_u32le(sect_hdr, 0, 0)
    _write_u32le(sect_hdr, 4, 0)
    _write_u32le(sect_hdr, 8, section_size)
    _write_u32le(sect_hdr, 12, 1)  # BOOTABLE

    tag_cmd = bytearray(16)
    tag_cmd[1] = 0x01  # ROM_TAG_CMD
    _write_u16le(tag_cmd, 2, 0)

    load_cmd = bytearray(16)
    load_cmd[1] = 0x02  # ROM_LOAD_CMD
    _write_u32le(load_cmd, 4, load_addr)
    _write_u32le(load_cmd, 8, len(payload))
    _write_u32le(load_cmd, 12, crc32(payload))

    jump_cmd = bytearray(16)
    jump_cmd[1] = 0x04  # ROM_JUMP_CMD
    _write_u32le(jump_cmd, 4, jump_addr)
    _write_u32le(jump_cmd, 8, 0)
    _write_u32le(jump_cmd, 12, jump_arg)

    payload_padded = _pad_to_block(payload)

    enc_header = aes_cbc_encrypt(key, iv, bytes(header))
    saved_iv = enc_header[:16]
    last_header_ct = enc_header[-16:]
    enc_sect_hdr = aes_cbc_encrypt(key, last_header_ct, bytes(sect_hdr))

    section_iv = saved_iv
    enc_tag_cmd = aes_cbc_encrypt(key, section_iv, bytes(tag_cmd))
    section_iv = saved_iv
    enc_load_cmd = aes_cbc_encrypt(key, section_iv, bytes(load_cmd))
    section_iv = enc_load_cmd[-16:]
    enc_payload = aes_cbc_encrypt(key, section_iv, bytes(payload_padded))
    section_iv = enc_payload[-16:]
    enc_jump_cmd = aes_cbc_encrypt(key, section_iv, bytes(jump_cmd))

    return (
        enc_header
        + enc_sect_hdr
        + enc_tag_cmd
        + enc_load_cmd
        + enc_payload
        + enc_jump_cmd
    )


def build_sb_fill_image(
    fill_addr: int,
    fill_count: int,
    fill_pattern: int,
    jump_addr: int = 0x00002000,
    jump_arg: int = 0,
):
    """Build an SB image with TAG + FILL + JUMP using the zero key."""
    key = bytes(16)
    iv = bytes(16)

    header_blocks = 6
    sect_hdr_blocks = 1
    first_boot_tag_block = header_blocks + sect_hdr_blocks
    section_size = 1 + 1 + 1  # TAG + FILL + JUMP
    total_blocks = first_boot_tag_block + section_size

    header = _build_plain_header(
        first_boot_tag_block=first_boot_tag_block,
        image_blocks=total_blocks,
    )

    sect_hdr = bytearray(16)
    _write_u32le(sect_hdr, 0, 0)
    _write_u32le(sect_hdr, 4, 0)
    _write_u32le(sect_hdr, 8, section_size)
    _write_u32le(sect_hdr, 12, 1)

    tag_cmd = bytearray(16)
    tag_cmd[1] = 0x01

    fill_cmd = bytearray(16)
    fill_cmd[1] = 0x03  # ROM_FILL_CMD
    _write_u32le(fill_cmd, 4, fill_addr)
    _write_u32le(fill_cmd, 8, fill_count)
    _write_u32le(fill_cmd, 12, fill_pattern)

    jump_cmd = bytearray(16)
    jump_cmd[1] = 0x04
    _write_u32le(jump_cmd, 4, jump_addr)
    _write_u32le(jump_cmd, 8, 0)
    _write_u32le(jump_cmd, 12, jump_arg)

    enc_header = aes_cbc_encrypt(key, iv, bytes(header))
    saved_iv = enc_header[:16]
    last_header_ct = enc_header[-16:]
    enc_sect_hdr = aes_cbc_encrypt(key, last_header_ct, bytes(sect_hdr))

    section_iv = saved_iv
    enc_tag_cmd = aes_cbc_encrypt(key, section_iv, bytes(tag_cmd))
    section_iv = saved_iv
    enc_fill_cmd = aes_cbc_encrypt(key, section_iv, bytes(fill_cmd))
    section_iv = enc_fill_cmd[-16:]
    enc_jump_cmd = aes_cbc_encrypt(key, section_iv, bytes(jump_cmd))

    return enc_header + enc_sect_hdr + enc_tag_cmd + enc_fill_cmd + enc_jump_cmd


def build_nand_boot_image(sb_image: bytes):
    """Build a minimal NAND image containing NCB, LDLB, and SB firmware."""
    page_size = 2048
    pages_per_block = 64
    block_size = page_size * pages_per_block

    fw_pages = math.ceil(len(sb_image) / page_size)
    fw_padded = bytearray(fw_pages * page_size)
    fw_padded[:] = b"\xff" * len(fw_padded)
    fw_padded[:len(sb_image)] = sb_image

    ncb = bytearray(page_size)
    ncb[:] = b"\xff" * page_size
    _write_u32le(ncb, 0, 0x504D5453)  # 'STMP' as little-endian
    ncb[4] = 10
    ncb[5] = 8
    ncb[6] = 5
    ncb[7] = 6
    _write_u32le(ncb, 8, page_size)
    _write_u32le(ncb, 12, page_size + 64)
    _write_u32le(ncb, 16, pages_per_block)
    _write_u32le(ncb, 20, 0)
    _write_u32le(ncb, 24, 0)
    _write_u32le(ncb, 28, 1)
    _write_u32le(ncb, 44, 0x2042434E)  # 'NCB '
    _write_u32le(ncb, 48, 2)
    _write_u32le(ncb, 52, 2)
    _write_u32le(ncb, 56, 1)
    _write_u32le(ncb, 60, 1)
    _write_u32le(ncb, 64, 0)
    _write_u32le(ncb, 68, 1)
    _write_u32le(ncb, 128, 0x4E494252)  # 'RBIN'

    ldlb = bytearray(page_size)
    ldlb[:] = b"\xff" * page_size
    _write_u32le(ldlb, 0, 0x504D5453)
    _write_u16le(ldlb, 4, 1)
    _write_u16le(ldlb, 6, 0)
    _write_u16le(ldlb, 8, 0)
    _write_u16le(ldlb, 10, 0)
    _write_u32le(ldlb, 12, 1)
    _write_u32le(ldlb, 44, 0x424C444C)  # 'LDLB'
    fw_start_block = 2
    fw_start_page = fw_start_block * pages_per_block
    _write_u32le(ldlb, 48, 0)
    _write_u32le(ldlb, 52, fw_start_page)
    _write_u32le(ldlb, 56, 0)
    _write_u32le(ldlb, 60, fw_pages)
    _write_u32le(ldlb, 128, 0x4C494252)  # 'RBIL'

    nand_image = bytearray(3 * block_size)
    nand_image[:] = b"\xff" * len(nand_image)
    nand_image[0 * block_size:0 * block_size + page_size] = ncb
    nand_image[1 * block_size:1 * block_size + page_size] = ldlb
    nand_image[2 * block_size:2 * block_size + len(fw_padded)] = fw_padded

    return bytes(nand_image)


def _sb_command_checksum(cmd: bytearray):
    cksum = 90
    for i in range(1, 16):
        cksum = (cksum + cmd[i]) & 0xFF
    cmd[0] = cksum


def build_existos_sb_image(
    payload: bytes,
    load_addr: int,
    jump_addr: int,
    jump_arg: int = 0xCAFEBABE,
):
    """Build an ExistOS-format SB image (plaintext header + real_key section)."""
    payload_blocks = math.ceil(len(payload) / SB_BLOCK_SIZE)
    load_padded = _pad_to_block(payload)

    header_blocks = 6
    sect_hdr_blocks = 1
    key_dict_blocks = 2
    tag_block = header_blocks + sect_hdr_blocks + key_dict_blocks
    section_size = 1 + payload_blocks + 1
    digest_blocks = 2
    total_blocks = tag_block + 1 + section_size + digest_blocks

    header_pt = bytearray(96)
    _write_bytes(header_pt, 20, b"STMP")
    header_pt[24] = 1
    header_pt[25] = 1
    _write_u16le(header_pt, 26, 0)
    _write_u32le(header_pt, 28, total_blocks)
    _write_u32le(header_pt, 32, tag_block)
    _write_u32le(header_pt, 36, 0)
    _write_u16le(header_pt, 40, 1)
    _write_u16le(header_pt, 42, header_blocks + sect_hdr_blocks)
    _write_u16le(header_pt, 44, header_blocks)
    _write_u16le(header_pt, 46, 1)
    _write_u16le(header_pt, 48, 1)
    _write_bytes(header_pt, 52, b"sgtl")
    _write_u16le(header_pt, 64, 1)
    _write_u16le(header_pt, 76, 1)
    _write_u16le(header_pt, 88, 0x50)

    header_tail = header_pt[20:]
    header_pt[:20] = sha1(bytes(header_tail))

    sect_hdr = bytearray(16)
    _write_u32le(sect_hdr, 0, 0)
    _write_u32le(sect_hdr, 4, tag_block + 1)
    _write_u32le(sect_hdr, 8, section_size)
    _write_u32le(sect_hdr, 12, 1)

    real_key = random_bytes(16)
    zero_key = bytes(16)
    saved_iv = bytes(header_pt[:16])

    cbc_mac_data = bytes(header_pt) + bytes(sect_hdr)
    cbc_mac_result = aes_cbc_encrypt(zero_key, bytes(16), cbc_mac_data)
    cbc_mac = cbc_mac_result[-16:]

    enc_real_key = aes_cbc_encrypt(zero_key, saved_iv, real_key)
    key_dict = cbc_mac + enc_real_key

    tag_cmd = bytearray(16)
    tag_cmd[1] = 0x01
    _write_u16le(tag_cmd, 2, 0x0001)
    _write_u32le(tag_cmd, 4, 0)
    _write_u32le(tag_cmd, 8, section_size)
    _write_u32le(tag_cmd, 12, 1)
    _sb_command_checksum(tag_cmd)

    load_cmd = bytearray(16)
    load_cmd[1] = 0x02
    _write_u32le(load_cmd, 4, load_addr)
    _write_u32le(load_cmd, 8, len(payload))
    _write_u32le(load_cmd, 12, crc32(payload))
    _sb_command_checksum(load_cmd)

    jump_cmd = bytearray(16)
    jump_cmd[1] = 0x04
    _write_u32le(jump_cmd, 4, jump_addr)
    _write_u32le(jump_cmd, 8, 0)
    _write_u32le(jump_cmd, 12, jump_arg)
    _sb_command_checksum(jump_cmd)

    enc_tag = aes_cbc_encrypt(real_key, saved_iv, bytes(tag_cmd))
    sect_data = bytes(load_cmd) + bytes(load_padded) + bytes(jump_cmd)
    enc_sect_data = aes_cbc_encrypt(real_key, saved_iv, sect_data)

    file_so_far = bytes(header_pt) + bytes(sect_hdr) + key_dict + enc_tag + enc_sect_data
    file_sha1 = sha1(file_so_far)
    digest_plain = file_sha1 + random_bytes(12)
    enc_digest = aes_cbc_encrypt(real_key, saved_iv, digest_plain)

    return bytes(header_pt) + bytes(sect_hdr) + key_dict + enc_tag + enc_sect_data + enc_digest
