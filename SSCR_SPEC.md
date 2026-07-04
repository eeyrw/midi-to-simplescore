# SSCR 乐谱格式规范

## 1. 设计目标

| 目标 | 实现 |
|------|------|
| 字节值直接区分 delta / event | MSB 判别：`bit7=0` → delta，`bit7=1` → event |
| 多数事件单字节编码 | Note 0~61 直连 1 字节，62~127 扩展 2 字节；覆盖全音域 |
| 解析器极简 | 一次 `byte & 0x80` 完成分支，`byte >> 6` 二级分派 |
| 和弦紧凑 | 同一 tick 的多事件共享一个 delta |
| 安全 | 变长字段有上限，溢出即终止 |

---

## 2. 文件结构

```
Offset | Size | Field         | Type
-------|------|---------------|-----------
0      | 4    | Magic         | "SSCR" (0x53 0x53 0x43 0x52)
4      | 1    | Version       | uint8 = 0x02
5      | 1    | Flags         | uint8
6      | 2    | TickPerSecond | uint16 LE
8      | 4    | DataLength    | uint32 LE
12     | var  | Event Data    | 见 §3
```

Header 固定 12 字节。

### 2.1 Magic

ASCII 字符串 `SSCR`。用于快速识别文件格式。

### 2.2 Version

当前版本 `0x02`。解析器应检查此字段，拒绝不支持的版本。

### 2.3 Flags

| Bit | Name | 说明 |
|-----|------|------|
| 0   | VEL_NOTEON  | NoteOn 事件包含 1 字节 velocity |
| 1   | VEL_NOTEOFF | NoteOff 事件包含 1 字节 velocity |
| 2~7 | Reserved    | 必须为 0，解析器忽略 |

Velocity 值域 0~127，即 MIDI velocity 原始值。

### 2.4 TickPerSecond

`uint16` 小端序。目标设备的 tick 频率（Hz）。

设备 tick = `floor(absoluteTime_s × TickPerSecond)`

典型值 125（tick 间隔 8ms），可根据设备定时器精度调整。

### 2.5 DataLength

`uint32` 小端序。Event Data 段的总字节数（不含 header）。

---

## 3. Event Data 编码

### 3.1 总览

流结构：

```
[delta bytes] [event bytes] [delta bytes] [event bytes] ... [EndOfScore]
```

字节按 bit7 分为两个互斥域：

```
0x00 ~ 0x7F  (bit7=0)   Delta 字节
0x80 ~ 0xFF  (bit7=1)   Event 字节
```

### 3.2 Delta

每个 delta 由 1~4 个 delta 字节组成，**小端序** 6-bit chunk 编码。

```
Delta byte:
  bit7   bit6   bit5-0
   0      c     dddddd

  c = 1: 后续还有 delta 字节
  c = 0: 这是最后一个 delta 字节
  d    : 6 位数据
```

delta 值 = `d0 | (d1 << 6) | (d2 << 12) | (d3 << 18)`

| 值范围 | 字节数 | TickPerSecond=125 对应时长 |
|--------|--------|---------------------------|
| 0 ~ 63      | 1 | 0 ~ 0.5 秒   |
| 64 ~ 4095   | 2 | ~32 秒       |
| 4096 ~ 262K | 3 | ~35 分钟     |
| 262K ~ 16M  | 4 | ~37 小时     |

编码示例：

```
   5 → 0x05
  63 → 0x3F
  64 → 0x40 0x01
 500 → 0x74 0x07       (52 + 7×64 = 500)
4096 → 0x40 0x40 0x01  (0 + 0×64 + 1×4096)
```

### 3.3 Event

#### 3.3.1 字节布局

```
Event byte:
  bit7   bit6   bit5-0
   1      t     ssssss

  t = 0: NoteOff 组
  t = 1: NoteOn 组
  ssssss: note 值 (0~61) 或控制码 (62~63)
```

#### 3.3.2 码表

| 字节值 | 名称 | 含义 |
|--------|------|------|
| `0x80 ~ 0xBD` | NOFF_DIRECT | NoteOff, note = byte & 0x3F (0~61) |
| `0xBE` | EOS | EndOfScore，无后续字节，立即停止 |
| `0xBF` | NOFF_EXT | NoteOff 扩展，下一字节 = note (0~127) |
| `0xC0 ~ 0xFD` | NON_DIRECT | NoteOn, note = byte & 0x3F (0~61) |
| `0xFE` | RESERVED | 保留，解析器应停止 |
| `0xFF` | NON_EXT | NoteOn 扩展，下一字节 = note (0~127) |

#### 3.3.3 直连与扩展

note 范围 0~61 使用直连编码（1 字节），62~127 使用扩展编码（escape + note，2 字节）。**全音域 0~127 均可表示。**

直连范围覆盖 5 个八度。移调系统将曲目中心拉到 note 31 附近，可保证绝大多数音符落在直连范围内，最大化压缩效果。编码选择由生成器在转换时决定，解析器按统一规则分派。

#### 3.3.4 Velocity

当对应的 Flags bit 置位时，velocity 字节紧跟在 note 字节之后：

```
无 velocity (Flags=0):
  NON_DIRECT → [byte]

有 velocity (Flags bit0=1):
  NON_DIRECT → [byte] [velocity]

无 velocity (Flags=0):
  NON_EXT    → [0xFF] [note]

有 velocity (Flags bit0=1):
  NON_EXT    → [0xFF] [note] [velocity]
```

EndOfScore 和 RESERVED 无 velocity。

---

## 4. 解析算法

### 4.1 事件组

一个事件组 = 一个 delta 值 + 同一 tick 上的若干 event。和弦的多音共享同一个 delta。

### 4.2 Tick 驱动伪代码

```
Init(score, size):
  if size < 12 or magic != "SSCR": return false
  if dataLength > size - 12: return false
  flags = score[5]
  position = 12, length = dataLength
  nextEventTick = read_delta()
  finished = false

UpdateToTick(tick):
  while not finished and tick >= nextEventTick:
    peek byte
    if byte & 0x80:
      read + dispatch event (see §4.3)
    else:
      delta = read_delta()
      nextEventTick += delta
```

### 4.3 Delta 读取

```
read_delta():
  value = 0, shift = 0
  loop:
    if shift >= 24: break          // 4 字节保护
    byte = read()
    value |= (byte & 0x3F) << shift
    shift += 6
    if (byte & 0x40) == 0: break   // c=0, 末字节
  return value
```

### 4.4 Event 分派

```
dispatch(byte):
  group = byte & 0x40    // 0=NoteOff组, 1=NoteOn组
  sub   = byte & 0x3F

  if sub == 0x3E: return EOS       // 0xBE 或 0xFE

  if sub == 0x3F:                  // 0xBF 或 0xFF
    note = read()
  else:
    note = sub

  if group == 0:                   // NoteOff
    if flags & 0x02: read()        // skip velocity
    NoteOff(note)
  else:                            // NoteOn
    vel = 127
    if flags & 0x01: vel = read()
    NoteOn(note, vel)
```

---

## 5. 完整编码示例

Flags=0x00, TickPerSecond=125, 移调后音符值:

```
t=0.0s  NoteOn 60, 64, 67     (C4-E4-G4 和弦)
t=0.5s  NoteOff 60, 64, 67
t=0.5s  NoteOn 72             (C5)
t=1.0s  NoteOff 72
```

编码：

```
delta=0     → 0x00
NON 60      → 0xFC              (0xC0|60, 直连)
NON 64      → 0xFF 0x40         (扩展, 64>61)
NON 67      → 0xFF 0x43         (扩展)

delta=63    → 0x3F              (0.5s × 125 = 63)
NOFF 60     → 0xBC              (0x80|60)
NOFF 64     → 0xBF 0x40
NOFF 67     → 0xBF 0x43
NON 72      → 0xFF 0x48         (扩展)

delta=63    → 0x3F
NOFF 72     → 0xBF 0x48

EOS         → 0xBE
```

完整字节流（header 12 + data 28 = 40 字节）：

```
53 53 43 52  02 00  7D 00  1C 00 00 00    header
00   FC FF 40 FF 43                         t=0.000
3F   BC BF 40 BF 43 FF 48                   t=0.504
3F   BF 48                                  t=1.008
BE                                           EOS
```

---

## 6. 数据量参考

实测 5 首不同风格 MIDI 文件（125 TPS，无 velocity）：

| 曲目 | 时长 | NoteOn 数 | SSCR 大小 |
|------|------|-----------|-----------|
| Jolly Old Saint Nicholas | 19s | 95 | 271 B |
| 欢乐颂 | 34s | 213 | 926 B |
| We Three Kings | 33s | 135 | 477 B |
| 卡农 (George Winston) | 5m23s | 3924 | 13383 B |
| 1812 Overture | 60s | 5504 | 18618 B |

---

## 7. 实现注意事项

1. **全音域 0~127**: 直连 0~61（1 字节），扩展 62~127（2 字节）。生成器应利用移调将曲目中心拉到 note 31 附近，最大化直连命中率。
2. **EndOfScore 无 payload**: `0xBE` 后不再读字节。
3. **RESERVED (0xFE)**: 解析器应终止播放以保证向前兼容。
4. **delta 上限 4 字节**: 覆盖 37 小时时长，实际足够。超过截断。
5. **同一 tick 和弦**: 共享 delta，其中 delta=0 用 `0x00` 单字节编码。
6. **NoteOff velocity**: 若 flags bit1=1，解析器必须跳过该字节，即使不使用其值。这确保流同步。
7. **默认 velocity**: 未启用 velocity 时 NoteOn 力度默认为 127。
