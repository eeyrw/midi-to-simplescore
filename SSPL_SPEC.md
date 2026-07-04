# SSPL 多乐谱容器格式规范 v1.0

## 1. 概述

SSPL（Simple Score PlayList）是一种面向嵌入式设备的极简多乐谱容器格式。将多条 SSCR 乐谱打包为一个文件，通过固定大小的目录表实现随机/顺序访问。

## 2. 文件结构

```
Offset | Size | Field
-------|------|---------------
0      | 4    | Magic = "SSPL" (0x53 0x53 0x50 0x4C)
4      | 1    | Version = 0x01
5      | 1    | Flags = 0x00 (reserved)
6      | 2    | Count (uint16 LE)
8      | 4    | Reserved = 0x00000000
-------|------|---------------
12     | var  | Entry Table (8 × Count bytes)
-------|------|---------------
...    | var  | Score Data 0
...    | var  | Score Data 1
...    | var  | ...
```

### 2.1 Header（12 字节）

| Offset | Type     | Field   |
|--------|----------|---------|
| 0      | char[4]  | Magic   |
| 4      | uint8    | Version |
| 5      | uint8    | Flags   |
| 6      | uint16   | Count   |
| 8      | uint32   | Reserved|

Count 为乐谱条目数（1~65535）。

### 2.2 Entry Table（Count × 8 字节）

每条条目占 8 字节，按 Count 数连续排列：

| Offset | Type   | Field  | 说明 |
|--------|--------|--------|------|
| 0      | uint32 | Offset | SSCR 数据在文件中的字节偏移（从文件起始计） |
| 4      | uint32 | Size   | SSCR 数据字节长度 |

- Offset 和 Size 均为 **小端序**。
- SSCR 数据即 `SSCR_SPEC.md` 定义的完整 SSCR 文件（含 13 字节 header）。
- 条目的 Offset 应 ≥ (12 + Count × 8)，即不得覆盖目录表。
- 条目之间的数据块不必连续排列，但需确保 4 字节对齐。

### 2.3 Score Data 区

紧随目录表之后。每条 SSCR 数据块是完整的独立 SSCR 文件，可直接传给 `ScorePlayerV3_Init()` 使用。

## 3. 解析算法

### 3.1 播放全部乐谱

```
init(sspl_data, totalSize):
  if totalSize < 12 or magic != "SSPL": return error
  count = sspl_data[6] | (sspl_data[7] << 8)
  table = &sspl_data[12]

  current = 0
  play_entry(0)

play_entry(index):
  if index >= count: finished = true; return
  offset = table[index * 8 + 0..3] (uint32 LE)
  size   = table[index * 8 + 4..7] (uint32 LE)
  if offset + size > totalSize: error
  ScorePlayerV3_Init(player, &sspl_data[offset], size)

on_score_finished():
  current++
  play_entry(current)
```

### 3.2 随机访问

```
play_by_name(index):
  entry = table + index * 8
  ScorePlayerV3_Init(player, sspl_data + entry.offset, entry.size)
```

## 4. 数据结构 (C)

```c
#define SSPL_HEADER_SIZE      12
#define SSPL_ENTRY_SIZE       8
#define SSPL_MAGIC_0          'S'
#define SSPL_MAGIC_1          'S'
#define SSPL_MAGIC_2          'P'
#define SSPL_MAGIC_3          'L'
#define SSPL_VERSION          0x01

typedef struct {
    uint32_t offset;
    uint32_t size;
} SSPL_Entry;

typedef struct {
    const uint8_t*  data;
    uint32_t        totalSize;
    uint16_t        count;
    const SSPL_Entry* entries;
} SSPL_File;
```

## 5. 示例

3 首曲目的 SSPL 文件：

```
Header (12B):
  53 53 50 4C  01 00  03 00  00 00 00 00
  ^^^^^^^^^^^  ^^ ^^  ^^^^^^  ^^^^^^^^^^^
  SSPL         v1 fl  count=3 reserved

Entry Table (24B = 3×8):
  offset=36  size=745    # 欢乐颂 (12 + 24 = 36)
  offset=781 size=8208   # 卡农
  offset=8989 size=12703 # 1812序曲

Score Data (at offset 36):
  53 53 43 52 03 00 ...  (SSCR header + event data)

... (rest of scores)
```

## 6. 设计原则

- **无名称**：v1 不做曲名，由调用方维护外部曲目表
- **固定条目大小**：8 字节，无变长字段，编解码均 O(1)
- **无分块**：每条乐谱是完整独立的 SSCR 文件，可直接转发给播放器
- **4 字节对齐**：目录表天然对齐，数据区通过 generator 保证对齐
