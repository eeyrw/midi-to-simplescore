# SSCR Legacy 乐谱格式规范

## 1. 概述

Legacy 格式是 midi-to-simplescore 最早的编码方案。它**仅记录 NoteOn 事件**，使用固定块大小编码时间增量，不包含 NoteOff、力度和文件头。

**不推荐新项目使用。** 推荐迁移到 SSCR 格式（见 `SSCR_SPEC.md`）。

---

## 2. 设计约束

- 目标平台：8051 / AVR 等 8-bit MCU
- 核心假设：资源极度匮乏，解析器必须极小
- 代价：丢失 NoteOff 时序、力度信息，且音符 127 存在编码冲突（见 §5）

---

## 3. 编码规则

### 3.1 Delta 时间

时间增量以 **tick** 为单位，使用 255-byte 分块编码：

```
while delta >= 255:
    write 255
    delta -= 255
write delta
```

每个 delta 字节 ∈ [0, 255]。当值为 255 时，表示"还有至少 255 ticks"，后续还有 delta 字节。

**示例：**
| delta 值 | 编码 |
|----------|------|
| 0        | 0x00 |
| 100      | 0x64 |
| 255      | 0xFF |
| 256      | 0xFF 0x01 |
| 1000     | 0xFF 0xFF 0xFF 0xE8 |

### 3.2 Note 编码

每个音符占 1 字节：

```
bit7 = 和弦结束标记：1 = 当前和弦的最后一个音
bit6-0 = MIDI Note Number (0~127)
```

音符值已经过移调处理，范围 0~127。

### 3.3 和弦

同一 tick 时刻触发的多个音符组成**和弦**。和弦的最后一个音符 `bit7 = 1`，前面的音符 `bit7 = 0`。

```
和弦 C-E-G (60, 64, 67):
  3C  40  43        → 最后一个音 bit7=1
         ^^    
    实际输出: 0x3C 0x40 0xC3
```

### 3.4 EndOfScore

标记为 `0xFF`，对应 `(note=128) → 0xFF`。

**注意：** 解析器通常假设 `0xFF` 出现在数据末尾表示结束。由于旧格式**无文件头、无长度字段**，解析器无法区分流中部的合法 note 127 和弦结束标记与 EndOfScore。

---

## 4. 完整示例

MIDI 事件：
```
t=0.0s : C4(60)
t=0.5s : C4(60) + E4(64)  (和弦)
t=1.0s : E4(64)            (前一和弦结束，新单音)
```

TickPerSecond=125 → 0.5s = 62 ticks

编码：
```
delta=0     : 0x00
note=60     : 0x3C | 0x80 = 0xBC       (单音，和弦结束标记置位)

delta=62    : 0x3E
note=60     : 0x3C                       (和弦第一个音)
note=64     : 0x40 | 0x80 = 0xC0        (和弦第二个/最后一个)

delta=62    : 0x3E
note=64     : 0x40 | 0x80 = 0xC0        (单音)

EOF         : 0xFF
```

完整字节流：
```
00 BC  3E 3C C0  3E C0  FF
```

---

## 5. 已知问题

### 5.1 音符 127 与 EOF 冲突

当移调后音符值为 127 且该音为和弦最后一个音时：
```
(127) | 0x80 = 0xFF
```
与 EndOfScore 标记 **完全相同**。

**缓解措施：** 移调系统确保音符不落在 127（即 `upperBoundNote ≤ 126` 或调整移调值）。

### 5.2 无 NoteOff

播放器通过**超时**推断音符结束——即新 NoteOn 覆盖旧音符，或使用固定音长。这导致不能准确表达：
- 连音（legato）中的重叠
- 音符的实际延续时长
- 休止符

### 5.3 无力度

所有音符以最大力度播放。

### 5.4 大 delta 膨胀

255 字节分块对大时间间隔效率极低。例如 5000 ticks 的休止需要 20 个 `0xFF` 字节 + 最终值。

---

## 6. 解析器伪代码

```
while 未到数据末尾:
    # 读取 delta
    while True:
        b = read_byte()
        tick += b
        if b != 255: break
    
    # 读取和弦
    while True:
        note_byte = read_byte()
        if note_byte == 0xFF: return      # EndOfScore
        
        note = note_byte & 0x7F
        trigger_note_on(note)
        
        if note_byte & 0x80: break        # 和弦结束，读取下一个 delta
```

---

## 7. 迁移建议

| 需求 | 推荐格式 |
|------|---------|
| 新项目 | V3（`SSCR_V3_SPEC.md`） |
| 已有 legacy 部署 | 保持，新曲目考虑 V3 |
| 需 NoteOff / 力度 | SSCR（见 SSCR_SPEC.md） |
| 极限代码空间（<1KB ROM） | Legacy（解析器最小） |
