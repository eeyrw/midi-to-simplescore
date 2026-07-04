/*
 * SimpleScorePlayer_V3.c — SSCR 乐谱播放器
 *
 * 解析 SSCR 二进制格式（见 SSCR_SPEC.md），以 tick 驱动方式触发
 * NoteOn / NoteOff 回调。设计目标为嵌入式平台：无堆分配、无递归、
 * 所有边界检查内联。
 *
 * 格式要点:
 *   - 文件头 12 字节: Magic "SSCR" + Version(1) + Flags(1) +
 *                    TickPerSecond(2 LE) + DataLength(4 LE)
 *   - 字节按 MSB 分区: [0x00..0x7F] = delta, [0x80..0xFF] = event
 *   - Delta: 6-bit chunk，小端序，bit6=1 表示还有后续字节
 *   - Event: bit7=1, bit6=类型 (0=off,1=on), bit5-0=note(0~61) 或控制码
 *
 * 使用示例见文件末尾。
 */

#include <stdint.h>
#include <stdbool.h>

/* ------------------------------------------------------------------
 * 常量
 * ------------------------------------------------------------------ */

#define SSCR_HEADER_SIZE  12

/* ------------------------------------------------------------------
 * 播放器状态
 * ------------------------------------------------------------------ */

typedef struct {

    /* ---- 数据流 ---- */
    const uint8_t* data;       // 指向 Event Data 起始位置（不含 header）
    uint32_t        length;    // Event Data 总长度（字节）
    uint32_t        position;  // 当前读取偏移

    /* ---- 时序 ---- */
    uint32_t        nextEventTick;  // 下一个待触发事件的 tick 值
    uint32_t        currentTick;    // 最近一次 UpdateToTick() 传入的 tick

    /* ---- 状态 ---- */
    bool            finished;       // 播放结束（EOS 或错误）

    /* ---- Header 缓存 ---- */
    uint16_t        tickPerSecond;  // 用于换算的 tick 频率（记录用，解析器不直接使用）
    uint8_t         version;        // SSCR 版本号
    uint8_t         flags;          // 标志位: bit0=NoteOn有velocity, bit1=NoteOff有velocity

} ScorePlayerV3;

/* ------------------------------------------------------------------
 * 回调接口 — 由用户实现
 * ------------------------------------------------------------------ */

/** 触发一个音符开始发声
 *  @param note     MIDI note number (0~127)
 *  @param velocity 力度 (0~127)，flags 未启用时恒为 127 */
void Synth_NoteOn(uint8_t note, uint8_t velocity);

/** 触发一个音符停止发声
 *  @param note     MIDI note number (0~127) */
void Synth_NoteOff(uint8_t note);

/* ------------------------------------------------------------------
 * 内部辅助 — 带边界检查的单字节读取
 * ------------------------------------------------------------------ */

/** 从流中读取 1 字节并前进 position。
 *  @return 成功返回 true，超出 data 范围返回 false */
static bool read_byte(ScorePlayerV3* p, uint8_t* out)
{
    if (p->position >= p->length)
        return false;
    *out = p->data[p->position++];
    return true;
}

/** 预读 1 字节但不前进 position（用于 delta/event 分支判别）。
 *  @return 成功返回 true，超出 data 范围返回 false */
static bool peek_byte(ScorePlayerV3* p, uint8_t* out)
{
    if (p->position >= p->length)
        return false;
    *out = p->data[p->position];
    return true;
}

/* ------------------------------------------------------------------
 * Delta 解码
 * ------------------------------------------------------------------ */

/**
 * 读取一个 delta 值（6-bit 小端 chunk 编码）。
 *
 * 编码规则: 每个字节 bit7=0（delta 域），bit6=1 表示还有后续字节，
 * bit5-0 = 6 位数据。多个字节按小端序拼接。
 *
 * 上限: 4 字节（24-bit），超出触发溢出保护截断。
 *
 * @return delta 值（tick 数）
 */
static uint32_t read_delta(ScorePlayerV3* p)
{
    uint32_t value = 0;
    uint8_t  shift = 0;       // 当前累积的位偏移
    uint8_t  byte;

    while (read_byte(p, &byte))
    {
        // 取低 6 位数据，左移后并入 value
        value |= (uint32_t)(byte & 0x3F) << shift;
        shift  += 6;

        // bit6 = 0 → 这是 delta 的最后一个字节
        if (!(byte & 0x40))
            break;

        // 超过 4 字节 → 格式错误，截断
        if (shift >= 24)
            break;
    }

    return value;
}

/* ------------------------------------------------------------------
 * Event 解码
 * ------------------------------------------------------------------ */

/**
 * 处理一个 event 字节（前提: byte & 0x80 != 0）。
 *
 * Event 编码:
 *   bit7=1 bit6=type bit5-0=sub
 *
 *   NoteOff 组 (bit6=0):
 *     0x80..0xBD  直连 NoteOff, note = byte & 0x3F  (0~61)
 *     0xBE        EndOfScore，终止播放
 *     0xBF        扩展 NoteOff, 下一字节为 note 值
 *
 *   NoteOn 组 (bit6=1):
 *     0xC0..0xFD  直连 NoteOn,  note = byte & 0x3F  (0~61)
 *     0xFE        保留（终止播放）
 *     0xFF        扩展 NoteOn,  下一字节为 note 值
 *
 * Velocity: 当对应的 flags bit 置位时，velocity 紧跟在 note 字节之后。
 * NoteOff 的 velocity 会被读取并丢弃（维持流同步）。
 *
 * @param byte 当前事件字节（已校验 bit7=1）
 * @return 正常处理返回 true，EOS/Reserved/错误返回 false
 */
static bool handle_event(ScorePlayerV3* p, uint8_t byte)
{
    // bit6 提取事件组: 0 = NoteOff 系列, 1 = NoteOn 系列
    uint8_t group = byte & 0x40;
    // bit5-0 提取 note 值或控制码
    uint8_t sub   = byte & 0x3F;

    if (group == 0)
    {
        /* ======== NoteOff 系列 ======== */

        // 0xBE = EndOfScore，无后续字节，立即终止
        if (sub == 0x3E)
            return false;

        // 解析 note 值
        uint8_t note;
        if (sub == 0x3F)
        {
            // 0xBF: 扩展模式，下一字节为完整 note 值
            if (!read_byte(p, &note))
                return false;
        }
        else
        {
            // 直连模式: note 就在 sub 字段中 (0~61)
            note = sub;
        }

        // 如果 flags bit1 置位，跳过 velocity 字节（NoteOff 不使用）
        if (p->flags & 0x02)
        {
            uint8_t dummy;
            if (!read_byte(p, &dummy))
                return false;
        }

        Synth_NoteOff(note);
    }
    else
    {
        /* ======== NoteOn 系列 ======== */

        // 0xFE = 保留，遇到即终止
        if (sub == 0x3E)
            return false;

        // 解析 note 值
        uint8_t note;
        if (sub == 0x3F)
        {
            // 0xFF: 扩展模式，下一字节为完整 note 值
            if (!read_byte(p, &note))
                return false;
        }
        else
        {
            // 直连模式: note 在 sub 字段中 (0~61)
            note = sub;
        }

        // 默认力度 127，若 flags bit0 置位则从流中读取实际值
        uint8_t vel = 127;
        if (p->flags & 0x01)
        {
            if (!read_byte(p, &vel))
                return false;
        }

        Synth_NoteOn(note, vel);
    }

    return true;
}

/* ==================================================================
 * 公开 API
 * ================================================================== */

/**
 * 初始化播放器，解析 SSCR header。
 *
 * @param p         播放器实例指针
 * @param score     完整的 SSCR 数据（含 12 字节 header）
 * @param totalSize score 数组总长度（字节）
 * @return 成功返回 true，header 无效或长度不足返回 false
 */
bool ScorePlayerV3_Init(ScorePlayerV3* p, const uint8_t* score, uint32_t totalSize)
{
    // ---- 校验最小长度 ----
    if (totalSize < SSCR_HEADER_SIZE)
        return false;

    // ---- 校验 Magic ----
    if (score[0] != 'S' || score[1] != 'S' ||
        score[2] != 'C' || score[3] != 'R')
        return false;

    // ---- 解析 header 字段 ----
    p->version       = score[4];
    p->flags         = score[5];
    // TickPerSecond: uint16 little-endian
    p->tickPerSecond = score[6] | (score[7] << 8);

    // DataLength: uint32 little-endian
    uint32_t dataLength =
        (uint32_t)score[8]        |
        (uint32_t)score[9]  << 8  |
        (uint32_t)score[10] << 16 |
        (uint32_t)score[11] << 24;

    // 减法防溢出: 确保 dataLength 不超出实际可用空间
    if (dataLength > totalSize - SSCR_HEADER_SIZE)
        return false;

    // ---- 初始化数据流 ----
    p->data     = &score[SSCR_HEADER_SIZE];  // 跳过 header
    p->length   = dataLength;
    p->position = 0;

    // ---- 初始化时序 ----
    p->currentTick    = 0;
    p->finished       = false;
    // 读取第一个 delta，确定首个事件的触发时刻
    p->nextEventTick  = read_delta(p);

    return true;
}

/**
 * 将播放器推进到指定 tick，触发该时刻及之前所有未处理的事件。
 *
 * 调用约定: 每 tick 调用一次（或在 tick 变化时调用）。
 * 无需在空闲 tick 反复轮询——内部 while 循环会一次性处理所有到期事件。
 *
 * @param p    播放器实例指针
 * @param tick 当前系统 tick 值（单调递增）
 */
void ScorePlayerV3_UpdateToTick(ScorePlayerV3* p, uint32_t tick)
{
    if (p->finished)
        return;

    p->currentTick = tick;

    // 处理所有 tick <= currentTick 的待触发事件
    while (!p->finished && p->currentTick >= p->nextEventTick)
    {
        uint8_t byte;

        // 预读 1 字节，通过 MSB 判定接下来是 delta 还是 event
        if (!peek_byte(p, &byte))
        {
            p->finished = true;
            break;
        }

        if (byte & 0x80)
        {
            /* ---- Event 模式 ---- */
            // 正式读出该字节
            if (!read_byte(p, &byte))
            {
                p->finished = true;
                break;
            }

            // 分派到事件处理器
            if (!handle_event(p, byte))
            {
                p->finished = true;
                break;
            }
            // 注意: 处理完一个 event 后继续循环，peek 下一个字节。
            // 如果仍是 event (bit7=1)，说明同一 tick 还有更多事件（和弦）；
            // 如果是 delta (bit7=0)，下一轮将进入 delta 模式。
        }
        else
        {
            /* ---- Delta 模式 ---- */
            // 当前 tick 的事件已全部处理完，读取下一个时间间隔
            uint32_t delta = read_delta(p);
            p->nextEventTick += delta;
            // 继续循环，检查新 nextEventTick 是否仍 <= currentTick
        }
    }
}

/**
 * 获取当前播放器所处的 tick 值。
 *
 * @param p 播放器实例指针
 * @return 最近一次 UpdateToTick 传入的 tick（不会超过该值）
 */
uint32_t ScorePlayerV3_GetCurrentTick(ScorePlayerV3* p)
{
    return p->currentTick;
}

/**
 * 查询播放是否已结束。
 *
 * @param p 播放器实例指针
 * @return 已结束返回 true（遇到 EOS、数据错误、或读完所有事件）
 */
bool ScorePlayerV3_IsFinished(ScorePlayerV3* p)
{
    return p->finished;
}

/* ==================================================================
 * 使用示例
 * ================================================================== */
/*
#include "scoreData.h"    // 由 MidiToSimpleScore.py 生成

ScorePlayerV3 player;

int main(void)
{
    // 初始化
    if (!ScorePlayerV3_Init(&player, scoreData, sizeof(scoreData)))
        while (1);   // header 无效，挂起

    uint32_t lastTick = 0;

    while (1)
    {
        uint32_t currentTick = GetSystemTick();  // 由用户实现的系统 tick

        // 仅在 tick 变化时更新（避免同一 tick 重复处理）
        if (currentTick != lastTick)
        {
            lastTick = currentTick;
            ScorePlayerV3_UpdateToTick(&player, currentTick);
        }

        // 其他主循环逻辑 ...
    }
}
*/
