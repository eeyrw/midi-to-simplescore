/*
 * sscr_player.c — SSCR 单乐谱播放器
 *
 * 解析 SSCR 二进制格式，以 tick 驱动方式触发回调。
 * 自动还原编码移调——回调收到的 note 已是原始 MIDI 音高。
 * 设计为单文件库：直接 #include 到项目中即可使用。
 *
 * 依赖: <stdint.h>, <stdbool.h>
 *
 * 用户必须实现:
 *   void SSCR_SynthNoteOn(uint8_t note, uint8_t velocity);
 *   void SSCR_SynthNoteOff(uint8_t note);
 */

#ifndef SSCR_PLAYER_C
#define SSCR_PLAYER_C

#include <stdint.h>
#include <stdbool.h>

/* ==================================================================
 * 常量
 * ================================================================== */

#define SSCR_HEADER_SIZE  13

/* ==================================================================
 * 数据结构
 * ================================================================== */

typedef struct {
    const uint8_t* data;
    uint32_t        length;
    uint32_t        position;

    uint32_t        nextEventTick;
    uint32_t        currentTick;
    bool            finished;

    uint16_t        tickPerSecond;
    int8_t          totalTranspose;
    uint8_t         version;
    uint8_t         flags;
} SSCR_Player;

/* ==================================================================
 * 回调 — 用户实现
 * ================================================================== */

extern void SSCR_SynthNoteOn(uint8_t note, uint8_t velocity);
extern void SSCR_SynthNoteOff(uint8_t note);

/* ==================================================================
 * 内部: 带边界检查的字节读取
 * ================================================================== */

static bool sscr_read_byte(SSCR_Player* p, uint8_t* out)
{
    if (p->position >= p->length) return false;
    *out = p->data[p->position++];
    return true;
}

static bool sscr_peek_byte(SSCR_Player* p, uint8_t* out)
{
    if (p->position >= p->length) return false;
    *out = p->data[p->position];
    return true;
}

/* ==================================================================
 * 内部: Delta 解码 (6-bit 小端 chunk)
 * ================================================================== */

static uint32_t sscr_read_delta(SSCR_Player* p)
{
    uint32_t value = 0;
    uint8_t  shift = 0;
    uint8_t  byte;

    while (sscr_read_byte(p, &byte))
    {
        value |= (uint32_t)(byte & 0x3F) << shift;
        shift  += 6;
        if (!(byte & 0x40)) break;
        if (shift >= 24)    break;
    }
    return value;
}

/* ==================================================================
 * 内部: Event 解码
 * ================================================================== */

static bool sscr_handle_event(SSCR_Player* p, uint8_t byte)
{
    uint8_t group = byte & 0x40;
    uint8_t sub   = byte & 0x3F;

    if (group == 0)
    {
        if (sub == 0x3E) return false;    // 0xBE = EndOfScore

        uint8_t note;
        if (sub == 0x3F)                   // 0xBF = NoteOff ext
        {
            if (!sscr_read_byte(p, &note)) return false;
        }
        else
        {
            note = sub;
        }

        if (p->flags & 0x02)              // skip NoteOff velocity
        {
            uint8_t dummy;
            if (!sscr_read_byte(p, &dummy)) return false;
        }

        note = (uint8_t)((int)note - p->totalTranspose);
        SSCR_SynthNoteOff(note);
    }
    else
    {
        if (sub == 0x3E) return false;    // 0xFE = Reserved

        uint8_t note;
        if (sub == 0x3F)                   // 0xFF = NoteOn ext
        {
            if (!sscr_read_byte(p, &note)) return false;
        }
        else
        {
            note = sub;
        }

        uint8_t vel = 127;
        if (p->flags & 0x01)
        {
            if (!sscr_read_byte(p, &vel)) return false;
        }

        note = (uint8_t)((int)note - p->totalTranspose);
        SSCR_SynthNoteOn(note, vel);
    }

    return true;
}

/* ==================================================================
 * 公开 API
 * ================================================================== */

/**
 * 初始化播放器。
 *
 * @param p         播放器实例
 * @param data      完整 SSCR 数据（含 13 字节 header）
 * @param totalSize 数据总长度
 * @return 成功返回 true
 */
bool SSCR_Init(SSCR_Player* p, const uint8_t* data, uint32_t totalSize)
{
    if (totalSize < SSCR_HEADER_SIZE) return false;
    if (data[0]!='S' || data[1]!='S' || data[2]!='C' || data[3]!='R')
        return false;

    p->version = data[4];
    p->flags   = data[5];
    p->tickPerSecond = data[6] | ((uint16_t)data[7] << 8);

    uint32_t dataLen =
        (uint32_t)data[8]        |
        (uint32_t)data[9]  << 8  |
        (uint32_t)data[10] << 16 |
        (uint32_t)data[11] << 24;

    if (dataLen > totalSize - SSCR_HEADER_SIZE) return false;

    p->totalTranspose = (int8_t)data[12];
    p->data     = &data[SSCR_HEADER_SIZE];
    p->length   = dataLen;
    p->position = 0;

    p->currentTick   = 0;
    p->finished      = false;
    p->nextEventTick = sscr_read_delta(p);

    return true;
}

/**
 * 推进到指定 tick，触发到期事件。
 */
void SSCR_UpdateToTick(SSCR_Player* p, uint32_t tick)
{
    if (p->finished) return;

    p->currentTick = tick;

    while (!p->finished && p->currentTick >= p->nextEventTick)
    {
        uint8_t byte;
        if (!sscr_peek_byte(p, &byte))
        { p->finished = true; break; }

        if (byte & 0x80)
        {
            if (!sscr_read_byte(p, &byte))
            { p->finished = true; break; }

            if (!sscr_handle_event(p, byte))
            { p->finished = true; break; }
        }
        else
        {
            uint32_t delta = sscr_read_delta(p);
            p->nextEventTick += delta;
        }
    }
}

/** 获取当前 tick */
uint32_t SSCR_GetCurrentTick(SSCR_Player* p) { return p->currentTick; }

/** 是否播放结束 */
bool SSCR_IsFinished(SSCR_Player* p) { return p->finished; }

/**
 * 获取编码时施加的总移调值。
 *
 * 还原原始音高: originalNote = encodedNote - totalTranspose
 * 叠加用户键移: playNote = encodedNote - totalTranspose + keyShift
 */
int8_t SSCR_GetTotalTranspose(SSCR_Player* p) { return p->totalTranspose; }

#endif /* SSCR_PLAYER_C */
