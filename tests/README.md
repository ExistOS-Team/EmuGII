# STMP3770 测试程序

本目录包含用于测试 STMP3770 QEMU 模拟器的简单程序。

## 文件

- `hello.c` - 简单的"Hello World"程序，通过 Debug UART 输出
- `stmp3770.ld` - Linker script，将程序加载到 DRAM

## 构建

使用 SCons 构建测试程序：

```bash
# 仅构建测试程序
scons test

# 同时构建 QEMU 和测试程序
scons qemu test
```

生成的文件：
- `build/tests/hello.o` - 目标文件
- `build/tests/hello.elf` - ELF 可执行文件
- `build/tests/hello.bin` - 原始二进制文件（用于 QEMU）

## 运行

```bash
# 方式 1: 使用构建的 QEMU
build/qemu/build/qemu-system-arm -M stmp3770 -kernel build/tests/hello.bin -nographic

# 方式 2: 使用系统 QEMU (如果已安装 STMP3770 支持)
qemu-system-arm -M stmp3770 -kernel build/tests/hello.bin -nographic
```

预期输出：
```
Hello from STMP3770!
UART is working!
```

按 `Ctrl-A X` 退出 QEMU。

## 程序说明

`hello.c` 程序执行以下操作：

1. 直接访问 Debug UART 寄存器 (0x80070000)
2. 通过 UART 发送字符串
3. 进入无限循环

这是一个最小的 bare-metal 程序，不依赖任何库。

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

## 自定义程序

可以基于 `hello.c` 创建更复杂的测试程序：

```c
#define UART_BASE 0x80070000
#define UART_DR   (*(volatile unsigned int *)(UART_BASE + 0x00))

void _start(void) {
    // 你的代码
    UART_DR = 'H';
    UART_DR = 'i';
    
    while(1);
}
```

使用相同的 linker script 和构建命令即可。

## 调试

使用 GDB 调试：

```bash
# 启动 QEMU with GDB server
build/qemu/build/qemu-system-arm -M stmp3770 -kernel build/tests/hello.bin \\
    -nographic -s -S

# 在另一个终端连接 GDB
arm-none-eabi-gdb build/tests/hello.elf
(gdb) target remote :1234
(gdb) break _start
(gdb) continue
```
