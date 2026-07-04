# AGENTS.md — midi-to-simplescore 项目开发指南

## 项目概述

将标准 MIDI 文件转换为嵌入式微控制器可播放的紧凑乐谱数据。

## 文件结构

```
midi-to-simplescore/
├── MidiToSimpleScore.py          # 主转换器 (SSCR / Legacy)
├── MidiToSimpleScore_Legacy.py   # Legacy 独立脚本
├── SSPL_Packer.py                # 多曲 SSPL 容器打包
│
├── embedded/                     # 嵌入式 C 实现 (最终产物)
│   ├── sscr_player.c             #   SSCR 播放器 (单文件库, #include 使用)
│   ├── sspl_player.h             #   SSPL 容器解析器 (header-only)
│   ├── example_single.c          #   单曲示例
│   ├── example_playlist.c        #   多曲示例
│   └── Makefile
│
├── SSCR_SPEC.md                  # SSCR 二进制格式规范
├── SSPL_SPEC.md                  # SSPL 容器规范
├── SSCR_LEGACY_SPEC.md           # Legacy 格式规范
│
├── README.md
├── pyproject.toml
├── requirements.txt
├── template/                     # C 模板 (8051/AVR/generic)
└── .gitignore
```

## 开发流程

### 修改 Python 转换器

```bash
pip install -e .
# 或
python MidiToSimpleScore.py --midi song.mid --outputDir ./output
python SSPL_Packer.py *.mid -o playlist.sspl -c playlist_data.c
```

### 修改 C 播放器

```bash
cd embedded && make clean && make all
./example_single score.sscr
./example_playlist playlist.sspl
```

测试用 MIDI 文件位于 `/media/yuan/60AE34D2AE34A308/Users/yuan/Desktop/midi合集/` (478 首)。

## 核心设计约束

### 移调算法 (MidiToSimpleScore.py)

两级移调，解耦设计：

1. **Stage 1 — `calcTranspose`**: 乐器移调。对齐 `voiceCenterNote`(默认 C4=60)，修剪到 [0,127]。两边越界时取较小调整。
2. **Stage 2 — `calcEncodingTranspose`**: 编码移调。基于 voice 后的 centroid/low/high，激进拉向 30 最大化直连编码。仅防低音 < 0，高音超 61 走扩展编码不修。
3. **`--useExtraTranspose`**: 只替换 Stage 1，Stage 2 始终执行。

### SSCR 事件编码

- 字节 MSB 分区: [0x00-0x7F]=delta, [0x80-0xFF]=event
- Delta: 6-bit 小端 chunk, bit6=1 表示延续
- Event: bit6=类型(0=off,1=on), bit5-0=note(0~61) 或控制码
- 直连 0~61 (1字节), 扩展 62~127 (0xFF/0xBF + note_byte, 2字节)
- 播放器通过 header TotalTranspose 自动还原原始音高

### 编译约束

- C 代码 `gcc -std=c99 -Wall -Wextra -Os` 零警告
- 仅依赖 `<stdint.h>` `<stdbool.h>`，无堆分配/递归
- C 文件设计为直接 `#include` 使用（单文件库模式）
