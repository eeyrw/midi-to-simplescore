# MIDI to SimpleScore

将标准 MIDI 文件转换为嵌入式微控制器可播放的紧凑乐谱数据。

## 格式

| 格式 | 规范 | 说明 |
|------|------|------|
| **SSCR** | [SSCR_SPEC.md](SSCR_SPEC.md) | 单字节事件 + 6-bit delta，完整 NoteOn/Off + 力度 |
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

## 模板

工具通过模板系统生成 C 数组。内置模板：

| 模板 | 输出 |
|------|------|
| `8051_sdcc` | `__code unsigned char Score[N] = {...}` |
| `avr_gcc` | `const unsigned char Score[] PROGMEM = {...}` |
| `generic` | `const unsigned char Score[N] = {...}` |

模板占位符：`$ScoreMetaInfo` / `$ScoreDataLen` / `$ScoreData`

外部模板：`--extraTemplate my_template.c.template`

## 播放器

`SimpleScorePlayer_V3.c` — 嵌入式 C 播放器参考实现。

```c
#include "SimpleScorePlayer_V3.c"
#include "scoreData.h"

ScorePlayerV3 player;
ScorePlayerV3_Init(&player, scoreData, sizeof(scoreData));

while (1) {
    uint32_t tick = GetSystemTick();
    ScorePlayerV3_UpdateToTick(&player, tick);
}
```

回调：

```c
void Synth_NoteOn(uint8_t note, uint8_t velocity);
void Synth_NoteOff(uint8_t note);
```

## 依赖

| 包 | 用途 |
|----|------|
| `mido` | MIDI 解析 |
| `terminaltables` | 移调信息表格 |

## 许可

GNU General Public License v3.0
