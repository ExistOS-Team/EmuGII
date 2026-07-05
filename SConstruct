# EmuGII SCons 构建系统
# 用于构建 STMP3770 QEMU 模拟器

import os
import shutil
import subprocess

# 项目路径
PROJECT_ROOT = Dir('#').abspath
QEMU_SOURCE = os.path.join(PROJECT_ROOT, 'ThirdParty', 'qemu')
BUILD_DIR = os.path.join(PROJECT_ROOT, 'build')
QEMU_BUILD = os.path.join(BUILD_DIR, 'qemu')
QEMU_BUILDDIR = os.path.join(QEMU_BUILD, 'build')
PATCHES_DIR = os.path.join(PROJECT_ROOT, 'patches')
SRC_DIR = os.path.join(PROJECT_ROOT, 'src')

# SCons 环境
env = Environment(ENV=os.environ)

# 辅助函数：复制目录
def copy_tree(src, dst):
    """复制整个目录树"""
    import platform

    if os.path.exists(dst):
        print(f"清理现有目录: {dst}")
        # 在 Git Bash/MSYS2 下使用 rm -rf 更可靠
        if platform.system() != 'Windows' or os.environ.get('MSYSTEM'):
            result = subprocess.run(['rm', '-rf', dst], capture_output=True)
            if result.returncode != 0:
                print(f"  警告: rm 失败，尝试 Python 方法")
                try:
                    shutil.rmtree(dst)
                except Exception as e:
                    print(f"  错误: 无法清理目录: {e}")
                    return False
        else:
            try:
                shutil.rmtree(dst)
            except Exception as e:
                print(f"  错误: 无法清理目录: {e}")
                return False

    print(f"复制 {src} -> {dst} ...")

    # 优先使用 cp 命令 (在 MSYS2/Git Bash 下更快更可靠)
    if platform.system() != 'Windows' or os.environ.get('MSYSTEM'):
        result = subprocess.run(['cp', '-r', src, dst], capture_output=True)
        if result.returncode == 0:
            print(f"  复制完成")
            return True
        else:
            print(f"  cp 失败，尝试 Python 方法: {result.stderr.decode()}")

    # 回退到 Python 方法
    try:
        shutil.copytree(src, dst, symlinks=True, dirs_exist_ok=True)
        print(f"  复制完成")
        return True
    except Exception as e:
        print(f"错误: 复制失败: {e}")
        return False

# 辅助函数：应用补丁
def apply_patches(target, source, env):
    """复制源文件并应用 patches/ 下尚未应用的补丁到 QEMU 源码"""
    # source[0] 是 .copied 标记文件，QEMU 目录是其父目录
    qemu_dir = os.path.dirname(str(source[0]))
    marker_path = str(target[0])

    # 读取已应用补丁列表
    applied = set()
    if os.path.exists(marker_path):
        try:
            with open(marker_path, 'r') as f:
                applied = set(line.strip() for line in f if line.strip())
        except Exception as e:
            print(f"  警告: 无法读取补丁标记文件: {e}")

    # 复制我们的源文件
    print(">>> 复制 STMP3770 源文件到 QEMU 树...")

    files_to_copy = [
        ('src/include/hw/arm/stmp3770.h', 'include/hw/arm/stmp3770.h'),
        ('src/include/hw/audio/stmp3770_audio.h', 'include/hw/audio/stmp3770_audio.h'),
        ('src/include/hw/display/stmp3770_lcdif.h', 'include/hw/display/stmp3770_lcdif.h'),
        ('src/include/hw/gpio/stmp3770_pinctrl.h', 'include/hw/gpio/stmp3770_pinctrl.h'),
        ('src/include/hw/intc/stmp3770_icoll.h', 'include/hw/intc/stmp3770_icoll.h'),
        ('src/include/hw/misc/stmp3770_clkctrl.h', 'include/hw/misc/stmp3770_clkctrl.h'),
        ('src/include/hw/misc/stmp3770_digctl.h', 'include/hw/misc/stmp3770_digctl.h'),
        ('src/include/hw/misc/stmp3770_lradc.h', 'include/hw/misc/stmp3770_lradc.h'),
        ('src/include/hw/misc/stmp3770_power.h', 'include/hw/misc/stmp3770_power.h'),
        ('src/include/hw/misc/stmp3770_ocotp.h', 'include/hw/misc/stmp3770_ocotp.h'),
        ('src/include/hw/rtc/stmp3770_rtc.h', 'include/hw/rtc/stmp3770_rtc.h'),
        ('src/include/hw/timer/stmp3770_timer.h', 'include/hw/timer/stmp3770_timer.h'),
        ('src/include/hw/timer/stmp3770_pwm.h', 'include/hw/timer/stmp3770_pwm.h'),
        ('src/hw/timer/stmp3770_pwm.c', 'hw/timer/stmp3770_pwm.c'),
        ('src/include/hw/usb/stmp3770_usbphy.h', 'include/hw/usb/stmp3770_usbphy.h'),
        ('src/include/hw/usb/stmp3770_usb.h', 'include/hw/usb/stmp3770_usb.h'),
        ('src/hw/usb/stmp3770_usbphy.c', 'hw/usb/stmp3770_usbphy.c'),
        ('src/hw/usb/stmp3770_usb.c', 'hw/usb/stmp3770_usb.c'),
        ('src/include/hw/dma/stmp3770_dma.h', 'include/hw/dma/stmp3770_dma.h'),
        ('src/include/hw/block/stmp3770_gpmi.h', 'include/hw/block/stmp3770_gpmi.h'),
        ('src/include/hw/i2c/stmp3770_i2c.h', 'include/hw/i2c/stmp3770_i2c.h'),
        ('src/include/hw/ssi/stmp3770_ssp.h', 'include/hw/ssi/stmp3770_ssp.h'),
        ('src/hw/arm/stmp3770.c', 'hw/arm/stmp3770.c'),
        ('src/hw/arm/stmp3770-board.c', 'hw/arm/stmp3770-board.c'),
        ('src/hw/audio/stmp3770_audio.c', 'hw/audio/stmp3770_audio.c'),
        ('src/hw/display/stmp3770_lcdif.c', 'hw/display/stmp3770_lcdif.c'),
        ('src/hw/gpio/stmp3770_pinctrl.c', 'hw/gpio/stmp3770_pinctrl.c'),
        ('src/hw/intc/stmp3770_icoll.c', 'hw/intc/stmp3770_icoll.c'),
        ('src/hw/misc/stmp3770_clkctrl.c', 'hw/misc/stmp3770_clkctrl.c'),
        ('src/hw/misc/stmp3770_digctl.c', 'hw/misc/stmp3770_digctl.c'),
        ('src/hw/misc/stmp3770_lradc.c', 'hw/misc/stmp3770_lradc.c'),
        ('src/hw/misc/stmp3770_power.c', 'hw/misc/stmp3770_power.c'),
        ('src/hw/misc/stmp3770_ocotp.c', 'hw/misc/stmp3770_ocotp.c'),
        ('src/hw/rtc/stmp3770_rtc.c', 'hw/rtc/stmp3770_rtc.c'),
        ('src/hw/timer/stmp3770_timer.c', 'hw/timer/stmp3770_timer.c'),
        ('src/hw/dma/stmp3770_dma.c', 'hw/dma/stmp3770_dma.c'),
        ('src/hw/block/stmp3770_gpmi.c', 'hw/block/stmp3770_gpmi.c'),
        ('src/hw/i2c/stmp3770_i2c.c', 'hw/i2c/stmp3770_i2c.c'),
        ('src/hw/ssi/stmp3770_ssp.c', 'hw/ssi/stmp3770_ssp.c'),
    ]

    for src_file, dst_file in files_to_copy:
        src_path = os.path.join(PROJECT_ROOT, src_file)
        dst_path = os.path.join(qemu_dir, dst_file)
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        shutil.copy2(src_path, dst_path)
        print(f"  已复制: {dst_file}")

    # 将 QEMU 工作树统一归一化为 LF，避免 Windows 下的 CRLF 导致补丁/编译异常
    print(">>> 归一化 QEMU 源码行尾到 LF...")
    subprocess.run(
        ['git', '-C', qemu_dir, 'config', 'core.autocrlf', 'false'],
        capture_output=True
    )
    result = subprocess.run(
        ['git', '-C', qemu_dir, 'checkout', '--', '.'],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print("  警告: QEMU 行尾归一化失败，继续尝试应用补丁:")
        print(result.stderr)

    # 应用尚未应用过的 patches/ 下补丁
    print(">>> 应用构建系统补丁...")
    patch_files = sorted([
        f for f in os.listdir(PATCHES_DIR)
        if f.endswith('.patch')
    ])

    if not patch_files:
        print("  警告: patches/ 目录下没有 .patch 文件")

    newly_applied = []
    for patch_file in patch_files:
        if patch_file in applied:
            print(f"  已应用，跳过: {patch_file}")
            continue

        patch_path = os.path.join(PATCHES_DIR, patch_file)
        print(f"  应用补丁: {patch_file}")

        result = subprocess.run(
            ['patch', '-p1', '-d', qemu_dir, '--forward', '-i', patch_path],
            capture_output=True,
            text=True
        )
        output = result.stdout + result.stderr
        if result.returncode != 0:
            print(f"  错误: 补丁应用失败 {patch_file}:")
            print(output)
            return 1

        print(f"  成功: {patch_file}")
        newly_applied.append(patch_file)

    # 更新标记文件
    with open(marker_path, 'a') as f:
        for patch_file in newly_applied:
            f.write(patch_file + '\n')

    return None

# 辅助函数：配置 QEMU
def configure_qemu(target, source, env):
    """配置 QEMU 构建"""
    # source[0] 是 .patched 标记文件，QEMU 目录是其父目录
    qemu_dir = os.path.dirname(str(source[0]))
    # target[0] 是 .configured 标记文件，构建目录是其父目录
    build_dir = os.path.dirname(str(target[0]))

    os.makedirs(build_dir, exist_ok=True)

    print(">>> 配置 QEMU...")

    # 将 Windows 路径转换为 MSYS2 路径格式
    # D:\Projects\... -> /d/Projects/...
    import re
    build_dir_unix = os.path.abspath(build_dir).replace('\\', '/')
    # 转换盘符: D:/ -> /d/
    build_dir_unix = re.sub(r'^([A-Za-z]):', r'/\1', build_dir_unix).lower()

    print(f"  使用路径: {build_dir_unix}")

    # 使用 bash 并显式设置 Unix 风格路径
    qemu_dir_unix = os.path.abspath(qemu_dir).replace('\\', '/')
    qemu_dir_unix = re.sub(r'^([A-Za-z]):', r'/\1', qemu_dir_unix).lower()

    configure_cmd = [
        r'D:\Tools\msys64\usr\bin\bash.exe', '-lc',
        f'cd "{build_dir_unix}" && CC=gcc CXX=g++ "{qemu_dir_unix}/configure" --target-list=arm-softmmu --enable-debug --disable-werror --disable-vhost-user --disable-libvduse --disable-guest-agent'
    ]

    result = subprocess.run(
        configure_cmd,
        env=env['ENV']
    )

    if result.returncode != 0:
        print("错误: QEMU 配置失败")
        return result.returncode

    # 创建标记文件
    with open(str(target[0]), 'w') as f:
        f.write("Configured\n")

    return None

# 辅助函数:编译 QEMU
def build_qemu(target, source, env):
    """编译 QEMU"""
    build_dir = os.path.dirname(str(source[0]))

    print(">>> 编译 QEMU...")

    # 获取 CPU 核心数
    import multiprocessing
    nproc = multiprocessing.cpu_count()

    # 转换为 Unix 路径格式(用于 bash -c)
    import re
    build_dir_unix = os.path.abspath(build_dir).replace('\\', '/')
    build_dir_unix = re.sub(r'^([A-Za-z]):', r'/\1', build_dir_unix).lower()

    result = subprocess.run(
        [r'D:\Tools\msys64\usr\bin\bash.exe', '-lc',
         f'cd "{build_dir_unix}" && ninja qemu-system-arm.exe -j{nproc}'],
        env=env['ENV']
    )

    if result.returncode != 0:
        print("错误: QEMU 编译失败")
        return result.returncode

    # 创建标记文件
    qemu_binary = os.path.join(build_dir, 'qemu-system-arm')
    if os.path.exists(qemu_binary) or os.path.exists(qemu_binary + '.exe'):
        with open(str(target[0]), 'w') as f:
            f.write("Build complete\n")
        return None
    else:
        print("错误: QEMU 二进制文件未生成")
        return 1

# 构建步骤定义

# 1. 复制 QEMU 源码树
def copy_qemu_action(target, source, env):
    """复制 QEMU 源码树并创建标记文件"""
    if not copy_tree(str(source[0]), os.path.dirname(str(target[0]))):
        return 1
    with open(str(target[0]), 'w') as f:
        f.write("Copied\n")
    return None

copy_qemu = env.Command(
    os.path.join(QEMU_BUILD, '.copied'),
    Dir(QEMU_SOURCE),
    copy_qemu_action
)

# 2. 应用补丁
patched_qemu = env.Command(
    os.path.join(QEMU_BUILD, '.patched'),
    copy_qemu,
    apply_patches
)

# 3. 配置 QEMU
configured_qemu = env.Command(
    os.path.join(QEMU_BUILDDIR, '.configured'),
    patched_qemu,
    configure_qemu
)

# 4. 编译 QEMU
built_qemu = env.Command(
    os.path.join(QEMU_BUILDDIR, '.built'),
    configured_qemu,
    build_qemu
)

# 默认目标
Default(built_qemu)

# 清理目标
env.Clean(built_qemu, BUILD_DIR)

# 别名
env.Alias('qemu', built_qemu)
env.Alias('clean', [], Delete(BUILD_DIR))

# ============================================================
# 测试程序构建
# ============================================================

# ARM 交叉编译环境
arm_env = Environment(
    tools=['cc', 'link', 'ar', 'as'],
    CC='arm-none-eabi-gcc',
    AS='arm-none-eabi-as',
    LD='arm-none-eabi-ld',
    OBJCOPY='arm-none-eabi-objcopy',
    ENV=os.environ
)

# ARM 编译标志
arm_env.Append(
    CFLAGS=['-mcpu=arm926ej-s', '-mthumb-interwork', '-nostdlib',
            '-ffreestanding', '-O2', '-Wall'],
    LINKFLAGS=['-T', 'tests/stmp3770.ld', '-nostdlib'],
)

# 构建测试程序
TEST_BUILD = os.path.join(BUILD_DIR, 'tests')

# 编译 hello.c
hello_obj = arm_env.Object(
    os.path.join(TEST_BUILD, 'hello.o'),
    'tests/hello.c'
)

# 链接 hello.elf
hello_elf = arm_env.Command(
    os.path.join(TEST_BUILD, 'hello.elf'),
    hello_obj,
    '$LD $LINKFLAGS -o $TARGET $SOURCES'
)

# 生成 hello.bin
hello_bin = arm_env.Command(
    os.path.join(TEST_BUILD, 'hello.bin'),
    hello_elf,
    '$OBJCOPY -O binary $SOURCE $TARGET'
)

# 测试别名
arm_env.Alias('test', hello_bin)
arm_env.Clean(hello_bin, TEST_BUILD)

# 帮助信息
Help("""
EmuGII 构建系统
================

目标:
  scons              - 构建 QEMU (默认)
  scons qemu         - 构建 QEMU
  scons test         - 编译测试程序
  scons -c           - 清理构建目录

构建过程:
  1. 复制 ThirdParty/qemu 到 build/qemu
  2. 应用 src/ 下的源文件
  3. 应用 patches/ 下的补丁(如果有)
  4. 配置 QEMU
  5. 编译 QEMU

测试程序:
  scons test         - 编译 tests/hello.c 到 build/tests/hello.bin

生成的二进制文件:
  build/qemu/build/qemu-system-arm       - QEMU 模拟器
  build/tests/hello.bin                  - 测试程序

运行测试:
  build/qemu/build/qemu-system-arm -M stmp3770 -kernel build/tests/hello.bin -nographic
""")
