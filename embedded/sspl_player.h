/*
 * sspl_player.h — SSPL 多乐谱容器解析器
 *
 * 解析 SSPL 容器格式，提供条目遍历接口。
 * 依赖 sscr_player.c。
 *
 * 用法:
 *   #include "sscr_player.c"
 *   #include "sspl_player.h"
 *
 *   SSPL_File sspl;
 *   SSPL_Init(&sspl, data, size);
 *
 *   for (uint16_t i = 0; i < SSPL_GetCount(&sspl); i++) {
 *       SSCR_Player p;
 *       const uint8_t *d; uint32_t s;
 *       SSPL_GetEntry(&sspl, i, &d, &s);
 *       SSCR_Init(&p, d, s);
 *       while (!SSCR_IsFinished(&p)) { ... SSCR_UpdateToTick(&p, tick); }
 *   }
 */

#ifndef SSPL_PLAYER_H
#define SSPL_PLAYER_H

#include <stdint.h>
#include <stdbool.h>

#define SSPL_HEADER_SIZE  12
#define SSPL_ENTRY_SIZE   8

/* ==================================================================
 * 数据结构
 * ================================================================== */

/** 目录条目 */
typedef struct {
    uint32_t offset;
    uint32_t size;
} SSPL_Entry;

/** SSPL 容器 */
typedef struct {
    const uint8_t*    data;
    uint32_t          totalSize;
    uint16_t          count;
    const SSPL_Entry* entries;
} SSPL_File;

/* ==================================================================
 * API
 * ================================================================== */

/** 初始化 SSPL 容器解析器。 */
static bool SSPL_Init(SSPL_File* f, const uint8_t* data, uint32_t totalSize)
{
    if (totalSize < SSPL_HEADER_SIZE) return false;
    if (data[0] != 'S' || data[1] != 'S' ||
        data[2] != 'P' || data[3] != 'L') return false;
    if (data[4] != 0x01) return false;  // Version

    f->count = data[6] | ((uint16_t)data[7] << 8);

    uint32_t tableSize = (uint32_t)f->count * SSPL_ENTRY_SIZE;
    if (SSPL_HEADER_SIZE + tableSize > totalSize) return false;

    f->data      = data;
    f->totalSize = totalSize;
    f->entries   = (const SSPL_Entry*)(data + SSPL_HEADER_SIZE);
    return true;
}

/** 获取条目数 */
static uint16_t SSPL_GetCount(SSPL_File* f) { return f->count; }

/** 获取第 index 条 SSCR 数据指针和长度 */
static bool SSPL_GetEntry(SSPL_File* f, uint16_t index,
                          const uint8_t** outData, uint32_t* outSize)
{
    if (index >= f->count) return false;

    uint32_t offset = f->entries[index].offset;
    uint32_t size   = f->entries[index].size;

    if (offset + size > f->totalSize) return false;

    *outData = f->data + offset;
    *outSize = size;
    return true;
}

#endif /* SSPL_PLAYER_H */
