# EmuGII

EmuGII 是基于 QEMU 的 SigmaTel STMP3770 SoC 模拟器，当前目标硬件是
HP 39gII 计算器。

当前 machine model 对齐 HP 39gII：ARM926EJ-S、512 KiB 片上 SRAM、默认无外部
DRAM、通过 GPMI 挂载 NAND Flash、LCDIF 前面板显示与键盘输入，并已用于启动
ExistOS Hypervisor 和 System。

## 当前状态

- Machine 类型：`stmp3770`
- CPU：ARM926EJ-S
- 板级内存：`0x00000000` 起 512 KiB SRAM；只有显式提供 QEMU RAM 时才映射外部 DRAM
- 启动输入：`-bios` 或 `-kernel`，镜像加载到 SRAM 起始地址
- NAND 输入：第一个 `-drive if=none` 后端，连接到 GPMI
- 固件验证：`tests/ExistOS` 可启动 ExistOS Hypervisor 并进入 System
- UI：LCDIF 图形前面板包含 LCD、按键输入和状态指示；也支持纯串口 headless 运行

## 仓库结构

```text
EmuGII/
|-- src/                  STMP3770 SoC、board 和外设实现
|   |-- hw/arm/           SoC 容器与 stmp3770 machine
|   |-- hw/block/         GPMI NAND 与 BCH/ECC
|   |-- hw/display/       LCDIF 与 HP39GII 前面板
|   |-- hw/dma/           APBH/APBX DMA
|   |-- hw/gpio/          PINCTRL/GPIO 与键盘矩阵
|   |-- hw/misc/          CLKCTRL、DIGCTL、LRADC、OCOTP、POWER
|   |-- hw/rtc/           RTC/watchdog
|   |-- hw/timer/         TIMROT 与 PWM
|   |-- hw/usb/           USB PHY 与 OTG 寄存器模型
|   `-- include/hw/       复制进 QEMU 的设备头文件
|-- patches/              QEMU Kconfig/Meson 集成补丁
|-- tests/                STMP3770 裸机测试与 ExistOS fixture
|-- ThirdParty/qemu/      QEMU 子模块；按只读处理
|-- build/                生成的 QEMU 副本、构建产物和运行时文件
`-- SConstruct            顶层构建编排
```

构建采用非侵入式集成：

1. 复制 `ThirdParty/qemu` 到 `build/qemu`。
2. 将 `src/` 下的 STMP3770 源文件复制到生成的 QEMU 树。
3. 应用 `patches/*.patch`，完成 Kconfig/Meson 集成。
4. 配置并构建 `arm-softmmu`。

不要把 `ThirdParty/qemu` 或 `build/qemu` 当成源码修改入口。源码修改应落在
`src/`、`patches/` 和 `SConstruct`。

## 构建

当前 `SConstruct` 面向本机 Windows/MSYS2 环境，QEMU configure/build 阶段会调用
`D:\Tools\msys64\usr\bin\bash.exe`。如果 MSYS2 安装路径不同，需要先调整
`SConstruct`。

MSYS2 依赖：

```bash
pacman -S base-devel mingw-w64-x86_64-toolchain \
          mingw-w64-x86_64-glib2 mingw-w64-x86_64-pixman \
          mingw-w64-x86_64-ninja mingw-w64-x86_64-meson \
          python python-pip git
pip install scons
```

如果要构建 `scons test` 的裸机测试，还需要 ARM bare-metal 工具链：

```bash
pacman -S mingw-w64-x86_64-arm-none-eabi-gcc
```

构建 QEMU：

```powershell
scons
```

构建最小 UART 裸机测试：

```powershell
scons test
```

清理构建输出：

```powershell
scons -c
```

Windows 下主要产物：

```text
build\qemu\build\qemu-system-arm.exe
```

## 运行

运行最小裸机测试：

```powershell
.\build\qemu\build\qemu-system-arm.exe `
  -M stmp3770 `
  -kernel .\build\tests\hello.bin `
  -nographic
```

运行 SRAM 链接的固件：

```powershell
.\build\qemu\build\qemu-system-arm.exe `
  -M stmp3770 `
  -bios <firmware.bin> `
  -serial stdio
```

挂载 raw NAND 镜像到 GPMI：

```powershell
.\build\qemu\build\qemu-system-arm.exe `
  -M stmp3770 `
  -bios <firmware.bin> `
  -drive file=<flash.bin>,if=none,format=raw `
  -serial stdio
```

图形 LCD/前面板输出依赖当前 QEMU build 中可用的显示后端，例如 `-display gtk`。
`tests/ExistOS` 启动脚本默认使用 `-display none`，用于串口验证。

## ExistOS Fixture

`tests/ExistOS` 包含启动已验证 ExistOS 镜像所需的输入：

- `hypervisor-rom.bin`：通过 `-bios` 加载的 Hypervisor ROM
- `flash.initial.bin`：只读 128 MiB 初始 NAND 镜像，包含 System/FTL 内容
- `run-existos.ps1`：面向本地 QEMU build 的前台启动脚本
- `MANIFEST.txt`：二进制输入的来源路径、大小和 SHA256

从仓库根目录运行：

```powershell
.\tests\ExistOS\run-existos.ps1
```

脚本会将 `tests\ExistOS\flash.initial.bin` 复制为
`build\ExistOS\flash.bin`，并从这个可写运行时副本启动。GPMI 可能会在运行时镜像末尾追加
OOB metadata，用于跨 QEMU 重启持久化 NAND 元数据。

重置运行时 NAND 副本：

```powershell
.\tests\ExistOS\run-existos.ps1 -ResetFlash
```

运行但不持久化写入：

```powershell
.\tests\ExistOS\run-existos.ps1 -Snapshot
```

预期串口启动标记：

```text
Booting...
System Booting...
=============SYSTEM STATUS=================
```

## 硬件模型

| 区域 | 当前模型 |
|------|----------|
| CPU/board | ARM926EJ-S，HP 39gII machine，Boot ROM 风格 UART 初始化 |
| Memory | 512 KiB SRAM，16 KiB DFLPT RAM，可选外部 DRAM 映射 |
| ICOLL | 64 路中断输入，IRQ/FIQ 输出到 ARM CPU |
| CLKCTRL | ExistOS clock init 所需的 PLL、分频、门控复位行为 |
| DIGCTL | Chip ID、版本/复位相关寄存器、HCLK 风格计数器 |
| POWER | 电池/VDD/Core voltage 状态与 power-speed 寄存器 |
| PINCTRL/GPIO | GPIO bank 与 HP39GII 键盘矩阵注入 |
| TIMROT | 4 路 timer 与最小 rotary decoder 寄存器行为 |
| RTC | tick/alarm 行为与 watchdog reset request |
| OCOTP | 固件读取所需的 shadow/readout 寄存器 |
| APBH/APBX DMA | 链表 descriptor、PIO word、经外设 handler 的数据搬运 |
| GPMI NAND | raw NAND 后端，boot/ID/read/write/erase 路径，追加 OOB 持久化 |
| BCH/ECC | GPMI ECC read 使用的 completion/status 模型 |
| LCDIF | panel command/data 路径，framebuffer/前面板 console，按键输入 |
| Audio DAC/ADC | QEMU audio voice 与 APBX DMA 连接 |
| LRADC | 固件使用的寄存器模型和固定 ADC/电压值 |
| I2C | 寄存器级 idle/probe stub |
| SSP1/SSP2 | 寄存器级 probe stub |
| PWM | 寄存器级 PWM channel stub |
| USB PHY/OTG | 寄存器级 device-mode stub；当前没有 host-visible USB gadget |

## 内存映射

| 地址 | 大小 | 设备 |
|------|------|------|
| `0x00000000` | 512 KiB | SRAM |
| `0x40000000` | 可选 | 显式提供 QEMU RAM 时映射的外部 DRAM |
| `0x80000000` | 8 KiB | ICOLL |
| `0x80004000` | 8 KiB | APBH DMA |
| `0x80008000` | 8 KiB | BCH/ECC |
| `0x8000C000` | 8 KiB | GPMI |
| `0x80010000` | 8 KiB | SSP1 |
| `0x80018000` | 8 KiB | PINCTRL/GPIO |
| `0x8001C000` | 8 KiB | DIGCTL |
| `0x80024000` | 8 KiB | APBX DMA |
| `0x8002C000` | 8 KiB | OCOTP |
| `0x80030000` | 8 KiB | LCDIF |
| `0x80034000` | 8 KiB | SSP2 |
| `0x80040000` | 512 B | CLKCTRL |
| `0x80044000` | 512 B | POWER |
| `0x80048000` | 8 KiB | Audio DAC |
| `0x8004C000` | 8 KiB | Audio ADC |
| `0x80050000` | 8 KiB | LRADC |
| `0x80058000` | 8 KiB | I2C |
| `0x8005C000` | 8 KiB | RTC |
| `0x80064000` | 8 KiB | PWM |
| `0x80068000` | 8 KiB | TIMROT |
| `0x8006C000` | 8 KiB | App UART |
| `0x80070000` | 8 KiB | Debug UART |
| `0x8007C000` | 8 KiB | USB PHY |
| `0x80080000` | 4 KiB | USB OTG |
| `0x800C0000` | 16 KiB | DFLPT RAM |

权威常量见 `src/include/hw/arm/stmp3770.h`。

## 测试

`scons test` 当前只构建 `tests/hello.c`，输出为 `build\tests\hello.bin`。

更多 STMP3770 裸机测试源码直接放在 `tests/` 下，覆盖 NAND/GPMI、DMA、LCDIF、
keyboard、PWM、USB、audio 等路径。这些是手动或定向验证 fixture，尚未全部接入
SCons `test` alias。

`tests\data`、`tests\qemu-iotests` 和 `tests\tcg` 来自 QEMU 树，不是当前
STMP3770 验证主路径。

## 开发约束

- `ThirdParty/qemu` 按只读处理。
- 生成代码和运行时镜像放在 `build/`。
- 新增 emulated device 时，先在 `src/` 添加实现，再更新 `SConstruct` copy 规则，并在
  `patches/` 添加 Kconfig/Meson 补丁。
- 修改 QEMU build system 时，可在生成的 `build/qemu` 树里验证，再导出补丁到
  `patches/`，然后从干净构建树重建。
- 本地编辑器配置、`.clangd`、`.vscode/` 和生成的 `compile_commands.json` 不属于项目源码。

## 许可证

GNU GPL v2 or later, matching QEMU.

## 参考

- QEMU documentation: <https://www.qemu.org/docs/master/>
- ExistOS-For-HP39GII: <https://github.com/ExistOS-Team/ExistOS-For-HP39GII>
