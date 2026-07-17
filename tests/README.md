# STMP3770 测试程序

本目录包含用于测试 STMP3770 QEMU 模拟器的简单程序。

除了 bare-metal 测试程序外，本目录还包含 host-side `qtest` 回归脚本，
用于直接校验 STMP3770 模拟器的寄存器与中断契约。

## 目录结构

- `baremetal/` - 目标板内运行的裸机 C 测试程序
  - `common/` - 公共 UART 实现 (`uart.c`/`uart.h`) 和 linker script
    - `stmp3770.ld` - 将程序加载到 DRAM (0x40000000)
    - `stmp3770_sram.ld` - 将程序加载到 SRAM (0x00000000)
  - `hello/` - 最简单的 "Hello World" 程序
  - `audio/` / `dflpt/` / `gpmi/` / `keyboard/` / `lcdif/` / `nand/` / `pwm/` / `usb/` - 按外设分组的测试
- `unit/` - 宿主机 Python 单元测试（如 `test_build_helpers.py`）
- `stmp3770_contract/` - host-side `qtest` 契约回归 Python 测试套件
  - `framework/` - 运行框架（`QTestMachine`、`conftest.py`）
  - `helpers/` - 镜像/SB/NAND/DMA 等辅助函数
  - `*/` - 按外设分组的 pytest 测试模块

## 构建

使用 SCons 构建测试程序：

```bash
# 编译 tests/baremetal 下所有裸机测试程序
scons baremetal

# 编译裸机测试 + 运行 Python unit tests
scons test

# 运行 host-side qtest 契约回归（会先构建 QEMU）
scons qtest

# 同时构建 QEMU 和测试程序
scons qemu test
```

生成的文件（按外设分组）：
- `build/tests/baremetal/<peripheral>/<name>.o` - 目标文件
- `build/tests/baremetal/<peripheral>/<name>.elf` - ELF 可执行文件
- `build/tests/baremetal/<peripheral>/<name>.bin` - 原始二进制文件（用于 QEMU）
- `build/tests/.pyunit` - Python unit tests 完成标记
- `build/tests/.stmp3770_qtest` - qtest 回归完成标记

## 运行

```bash
# 方式 0: 运行 host-side qtest 契约回归
scons qtest

# 方式 1: 直接运行 pytest（从仓库根目录）
uv run pytest tests/unit -q
uv run pytest tests/stmp3770_contract -q

# 方式 2: 使用 EMUGII_QTEST_FILTER 过滤 qtest 契约
EMUGII_QTEST_FILTER='RTC' uv run pytest tests/stmp3770_contract -q

# 方式 3: 使用构建的 QEMU 运行单个裸机测试
build/qemu/build/qemu-system-arm -M stmp3770 \
    -kernel build/tests/baremetal/hello/hello.bin -nographic

# 方式 4: 使用系统 QEMU (如果已安装 STMP3770 支持)
qemu-system-arm -M stmp3770 \
    -kernel build/tests/baremetal/hello/hello.bin -nographic
```

`scons qtest` 会先构建 `build/qemu/build/qemu-system-arm`，再运行
`tests/stmp3770_contract/` 下的 pytest 测试套件。
`scons test` 会先通过 `scons baremetal` 编译所有裸机测试，再运行
`tests/unit/` 下的 pytest 单元测试。

## 环境变量

- `EMUGII_QEMU_BINARY` - QEMU 可执行文件路径
- `EMUGII_QEMU_CWD` - QEMU 工作目录
- `EMUGII_QTEST_FILTER` - 只运行契约名称/描述包含该子串的测试

## 程序说明

`baremetal/hello/hello.c` 程序执行以下操作：

1. 通过 `common/uart.h` 使能 Debug UART (0x80070000)
2. 调用 `uart_puts()` 发送字符串
3. 进入无限循环

所有 `tests/baremetal/*` 下的程序都共享 `baremetal/common/uart.c` 中的
`uart_putc` / `uart_puts` / `uart_puthex` 实现，避免重复实现 UART 输出代码。

## 依赖

需要 ARM 交叉编译工具链：

**Ubuntu/Debian:**
```bash
sudo apt-get install gcc-arm-none-eabi
```

**macOS (Homebrew):**
```bash
brew install arm-none-eabi-gcc
```

**Windows (MSYS2):**
```bash
pacman -S mingw-w64-x86_64-arm-none-eabi-gcc
```

运行 `scons qtest` 还需要：

- `uv`（Python 包管理器）
- 可运行 QEMU 构建的 MSYS2/MINGW `bash`
  - 可通过 `EMUGII_BASH` 或 `MSYS2_BASH` 指定
  - 否则构建系统会从 `PATH` 自动探测

## 自定义程序

可以基于 `baremetal/hello/hello.c` 创建更复杂的测试程序：

```c
#include "common/uart.h"

void _start(void) {
    // 你的代码
    UART_CR = CR_UARTEN | CR_TXE;
    uart_puts("Hi\n");

    while (1);
}
```

放在 `tests/baremetal/<peripheral>/` 目录下，`scons baremetal` 会自动编译。

## 调试

使用 GDB 调试：

```bash
# 启动 QEMU with GDB server
build/qemu/build/qemu-system-arm -M stmp3770 \\
    -kernel build/tests/baremetal/hello/hello.bin \\
    -nographic -s -S

# 在另一个终端连接 GDB
arm-none-eabi-gdb build/tests/baremetal/hello/hello.elf
(gdb) target remote :1234
(gdb) break _start
(gdb) continue
```
