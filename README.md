# MIDI to SimpleScore

将标准 MIDI 文件转换为嵌入式微控制器可播放的紧凑乐谱数据。

## 格式

| 格式 | 规范 | 说明 |
|------|------|------|
| **SSCR** | [SSCR_SPEC.md](SSCR_SPEC.md) | 单字节事件 + 6-bit delta，完整 NoteOn/Off + 力度 |
| **SSPL** | [SSPL_SPEC.md](SSPL_SPEC.md) | 多乐谱容器，固定目录表，极简解析 |
| SSCR Legacy | [SSCR_LEGACY_SPEC.md](SSCR_LEGACY_SPEC.md) | 仅 NoteOn，极简。新项目不推荐 |

## 安装

```bash
git clone https://github.com/eeyrw/midi-to-simplescore.git
cd midi-to-simplescore

python3 -m venv venv
source venv/bin/activate          # Linux / macOS
# venv\Scripts\activate           # Windows

pip install -e .
```

安装后提供两个 CLI 入口：

```bash
midi-to-simplescore --midi song.mid -o ./output          # SSCR 格式
midi-to-simplescore-legacy song.mid -o score.bin         # Legacy 格式
```

也可直接运行脚本：

```bash
python MidiToSimpleScore.py --midi song.mid --outputDir ./output
python MidiToSimpleScore_Legacy.py song.mid -o score.bin
```

## CLI 参数

```bash
midi-to-simplescore --help
```

| 参数 | 默认 | 说明 |
|------|------|------|
| `--midi` | (必选) | 输入 MIDI 文件路径 |
| `--outputDir` | `.` | 输出目录 |
| `--scoreFormat` | `v3` | `v3` (推荐) 或 `old` (legacy) |
| `--tickPerSecond` | `125` | 目标设备 tick 频率 |
| `--template` | `8051_sdcc` | `8051_sdcc` / `avr_gcc` / `generic` |
| `--extraTemplate` | — | 外部 `.template` 文件，覆盖内置模板 |
| `--voiceCenterNote` | `C:4` (60) | 目标音域中心音（MIDI note） |
| `--upperBoundNote` | `127` | 目标设备最高音 |
| `--lowerBoundNote` | `0` | 目标设备最低音 |
| `--transpose` | 自动 | 手动移调半音数，需配合 `--useExtraTranspose` |
| `--useExtraTranspose` | `false` | 启用手动移调 |
| `--includeNoteOnVelocity` | `false` | 保存 NoteOn 力度 |
| `--includeNoteOffVelocity` | `false` | 保存 NoteOff 力度 |

### 示例

```bash
# 默认 SSCR 输出
midi-to-simplescore --midi song.mid

# 指定模板 + 力度
midi-to-simplescore --midi song.mid --template avr_gcc --includeNoteOnVelocity

# Legacy 仅 NoteOn
midi-to-simplescore --midi song.mid --scoreFormat old

# 手动移调
midi-to-simplescore --midi song.mid --useExtraTranspose --transpose -3
```

## SSPL 多乐谱打包

将多条 MIDI 打包为一个 SSPL 容器文件，同时生成二进制和 C 数组：

```bash
# 二进制 + 内嵌 C 数组
python SSPL_Packer.py *.mid -o playlist.sspl -c playlist_data.c

# 带模板（8051/AVR）
python SSPL_Packer.py *.mid -o playlist.sspl -c playlist_data.c --template 8051_sdcc

# 手动移调
python SSPL_Packer.py *.mid -o playlist.sspl --useExtraTranspose --transpose -3
```

### SSPL Packer 参数

| 参数 | 默认 | 说明 |
|------|------|------|
| `midi_files` | (必选) | 输入 MIDI 文件（多个） |
| `-o, --output` | `playlist.sspl` | 输出 SSPL 二进制文件 |
| `-c, --c-output` | — | 输出 C 数组文件路径 |
| `--template` | — | C 模板名 (`8051_sdcc` / `avr_gcc` / `generic`) |
| `--voiceCenterNote` | `60` | 目标音域中心音 |
| `--tickPerSecond` | `125` | 目标设备 tick 频率 |
| `--includeNoteOnVelocity` | `false` | 保存 NoteOn 力度 |
| `--includeNoteOffVelocity` | `false` | 保存 NoteOff 力度 |
| `--useExtraTranspose` | `false` | 启用手动移调（跳过自动 Stage 1） |
| `--transpose` | `0` | 手动移调半音数，需配合 `--useExtraTranspose` |

生成的 C 头文件包含完整元信息注释（原始音域、乐器移调、编码移调、编码后音域）。

## 模板

工具通过模板系统生成 C 数组。内置模板：

| 模板 | 输出 |
|------|------|
| `8051_sdcc` | `__code unsigned char Score[N] = {...}` |
| `avr_gcc` | `const unsigned char Score[] PROGMEM = {...}` |
| `generic` | `const unsigned char Score[N] = {...}` |

模板占位符：`$ScoreMetaInfo` / `$ScoreDataLen` / `$ScoreData`

外部模板：`--extraTemplate my_template.c.template`

## embedded/ — 嵌入式 C 实现

所有嵌入式播放代码集中在 `embedded/` 目录，零堆分配、零递归，设计为直接 `#include` 使用。

```
embedded/
├── sscr_player.c        # SSCR 单曲播放器（单文件库）
├── sspl_player.h        # SSPL 多曲容器解析器（header-only）
├── example_single.c     # 单曲播放完整示例
├── example_playlist.c   # SSPL 多曲播放完整示例
└── Makefile             # make single / make playlist
```

**构建:**

```bash
cd embedded
make all          # 编译全部示例
./example_single score.sscr
./example_playlist playlist.sspl
```

### sscr_player.c

SSCR 单乐谱播放器。核心 API：

```c
#include "sscr_player.c"
#include "scoreData.h"

SSCR_Player p;
SSCR_Init(&p, scoreData, sizeof(scoreData));   // 自动读取 TotalTranspose 并还原音高

while (1) {
    uint32_t tick = GetSystemTick();
    SSCR_UpdateToTick(&p, tick);               // 触发到期事件
    if (SSCR_IsFinished(&p)) break;
}
```

用户需实现两个回调：

```c
void SSCR_SynthNoteOn (uint8_t note, uint8_t velocity);
void SSCR_SynthNoteOff(uint8_t note);
```

回调收到的 note 已是**还原后的原始 MIDI 音高**（播放器自动应用了 TotalTranspose 的逆运算）。

| API | 说明 |
|-----|------|
| `SSCR_Init(p, data, size)` | 初始化，校验 header，读取首个 delta |
| `SSCR_UpdateToTick(p, tick)` | 处理所有 tick 到期的 NoteOn/Off 事件 |
| `SSCR_IsFinished(p)` | 播放结束（EOS 或错误） |
| `SSCR_GetCurrentTick(p)` | 当前 tick 值 |
| `SSCR_GetTotalTranspose(p)` | header 中存储的总移调值 |

### sspl_player.h

SSPL 多乐谱容器解析器（header-only，需配合 `sscr_player.c` 使用）：

```c
#include "sscr_player.c"
#include "sspl_player.h"
#include "playlistData.h"

SSPL_File sspl;
SSPL_Init(&sspl, playlistData, sizeof(playlistData));

for (uint16_t i = 0; i < SSPL_GetCount(&sspl); i++) {
    const uint8_t *data; uint32_t size;
    SSPL_GetEntry(&sspl, i, &data, &size);       // 获取第 i 首的 SSCR 数据

    SSCR_Player p;
    SSCR_Init(&p, data, size);                   // 复用 SSCR 播放器
    while (!SSCR_IsFinished(&p))
        SSCR_UpdateToTick(&p, tick);
}
```

| API | 说明 |
|-----|------|
| `SSPL_Init(f, data, size)` | 解析 SSPL header + 目录表 |
| `SSPL_GetCount(f)` | 返回乐谱总数 |
| `SSPL_GetEntry(f, i, &outData, &outSize)` | 获取第 i 条 SSCR 数据指针和长度 |

### 编译要求

- C99 或更高
- `-Wall -Wextra -Os` 零警告
- 仅依赖 `<stdint.h>` `<stdbool.h>`，无任何运行时库依赖

## 依赖

| 包 | 用途 |
|----|------|
| `mido` | MIDI 解析 |
| `terminaltables` | 移调信息表格 |

## 许可

GNU General Public License v3.0
