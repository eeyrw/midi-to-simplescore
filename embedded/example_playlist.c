/*
 * example_playlist.c — 播放 SSPL 多乐谱容器
 *
 * 演示 SSPL 容器 + SSCR 播放器的联合用法。
 * 编译: gcc -std=c99 example_playlist.c -o example_playlist
 *
 * 用法: ./example_playlist <playlist.sspl>
 */

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>

/* ==================================================================
 * 回调 — 连接音频合成器
 * ================================================================== */

static uint16_t g_scoreIndex;
static uint16_t g_eventCount;

void SSCR_SynthNoteOn(uint8_t note, uint8_t velocity)
{
    (void)note; (void)velocity;
    g_eventCount++;
}

void SSCR_SynthNoteOff(uint8_t note)
{
    (void)note;
    g_eventCount++;
}

/* ==================================================================
 * 包含播放器
 * ================================================================== */

#include "sscr_player.c"
#include "sspl_player.h"

/* ==================================================================
 * 主程序
 * ================================================================== */

int main(int argc, char** argv)
{
    if (argc < 2)
    {
        printf("Usage: %s <playlist.sspl>\n", argv[0]);
        return 1;
    }

    FILE* fp = fopen(argv[1], "rb");
    if (!fp) { printf("Cannot open %s\n", argv[1]); return 1; }

    fseek(fp, 0, SEEK_END);
    long sz = ftell(fp); rewind(fp);

    uint8_t* buf = (uint8_t*)malloc((size_t)sz);
    if (fread(buf, 1, (size_t)sz, fp) != (size_t)sz)
    { printf("Read error\n"); free(buf); fclose(fp); return 1; }
    fclose(fp);

    /* 初始化 SSPL */
    SSPL_File sspl;
    if (!SSPL_Init(&sspl, buf, (uint32_t)sz))
    {
        printf("Invalid SSPL file\n");
        free(buf);
        return 1;
    }

    printf("SSPL: %u score(s)  total=%u bytes\n\n",
           SSPL_GetCount(&sspl), (uint32_t)sz);

    /* 逐首播放 */
    for (uint16_t i = 0; i < SSPL_GetCount(&sspl); i++)
    {
        const uint8_t* data;
        uint32_t       size;

        if (!SSPL_GetEntry(&sspl, i, &data, &size))
        {
            printf("  [%u] GET ENTRY FAILED\n", i);
            continue;
        }

        SSCR_Player player;
        if (!SSCR_Init(&player, data, size))
        {
            printf("  [%u] INVALID SSCR DATA\n", i);
            continue;
        }

        printf("--- Score %u/%u  offset=%u  size=%u  transposition=%d ---\n",
               i + 1, SSPL_GetCount(&sspl),
               (unsigned)sspl.entries[i].offset,
               (unsigned)size,
               SSCR_GetTotalTranspose(&player));

        g_scoreIndex = i;
        g_eventCount = 0;

        uint32_t tick = 0;
        while (!SSCR_IsFinished(&player))
        {
            SSCR_UpdateToTick(&player, tick);
            tick++;
        }

        printf("  Events: %u  Ticks: %u\n\n", g_eventCount, tick);
    }

    free(buf);
    printf("Playlist finished.\n");
    return 0;
}
