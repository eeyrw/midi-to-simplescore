/*
 * SSPL_Player.h — SSPL 多乐谱容器播放器
 *
 * 解析 SSPL 容器格式（SSPL_SPEC.md），按条目顺序依次播放 SSCR 乐谱。
 * 依赖 SimpleScorePlayer_V3.c。
 *
 * 无堆分配、无递归，适配嵌入式平台。
 */

#ifndef SSPL_PLAYER_H
#define SSPL_PLAYER_H

#include <stdint.h>
#include <stdbool.h>

#define SSPL_HEADER_SIZE  12
#define SSPL_ENTRY_SIZE   8

/* ------------------------------------------------------------------
 * 数据结构
 * ------------------------------------------------------------------ */

/** 目录条目（8 字节） */
typedef struct {
    uint32_t offset;   // SSCR 数据在文件中的偏移
    uint32_t size;     // SSCR 数据长度（字节）
} SSPL_Entry;

/** SSPL 容器解析状态 */
typedef struct {
    const uint8_t*  data;        // 完整 SSPL 文件数据指针
    uint32_t        totalSize;   // 文件总长度
    uint16_t        count;       // 乐谱条目数
    uint16_t        current;     // 当前播放到的索引
    const SSPL_Entry* entries;   // 目录表指针
} SSPL_Player;

/* ------------------------------------------------------------------
 * API
 * ------------------------------------------------------------------ */

/**
 * 初始化 SSPL 播放器。
 *
 * @param p         播放器实例指针
 * @param data      完整 SSPL 文件数据
 * @param totalSize 数据长度
 * @return 成功返回 true（Magic/Version 校验通过）
 */
static bool SSPL_Init(SSPL_Player* p, const uint8_t* data, uint32_t totalSize)
{
    if (totalSize < SSPL_HEADER_SIZE)
        return false;

    if (data[0] != 'S' || data[1] != 'S' ||
        data[2] != 'P' || data[3] != 'L')
        return false;

    if (data[4] != 0x01)           // Version
        return false;

    p->count = data[6] | ((uint16_t)data[7] << 8);
    p->current = 0;

    uint32_t tableSize = (uint32_t)p->count * SSPL_ENTRY_SIZE;
    if (SSPL_HEADER_SIZE + tableSize > totalSize)
        return false;

    p->data      = data;
    p->totalSize = totalSize;
    p->entries   = (const SSPL_Entry*)(data + SSPL_HEADER_SIZE);

    return true;
}

/**
 * 获取第 index 条 SSCR 数据的偏移和长度。
 *
 * @param p        播放器实例指针
 * @param index    条目索引 (0 ~ count-1)
 * @param outData  输出：SSCR 数据指针
 * @param outSize  输出：SSCR 数据长度
 * @return 成功返回 true
 */
static bool SSPL_GetEntry(SSPL_Player* p, uint16_t index,
                          const uint8_t** outData, uint32_t* outSize)
{
    if (index >= p->count)
        return false;

    uint32_t offset = p->entries[index].offset;
    uint32_t size   = p->entries[index].size;

    if (offset + size > p->totalSize)
        return false;

    *outData = p->data + offset;
    *outSize = size;
    return true;
}

/**
 * 获取乐谱条目总数。
 */
static uint16_t SSPL_GetCount(SSPL_Player* p)
{
    return p->count;
}

#endif /* SSPL_PLAYER_H */
