/*
 * example_single.c — 播放单条 SSCR 乐谱
 *
 * 演示 SSCR 播放器的基础用法。
 * 编译: gcc -std=c99 example_single.c -o example_single
 *
 * 用法: ./example_single <score_file.sscr>
 */

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdbool.h>

/* ==================================================================
 * 回调实现 — 连接到你的音频合成器
 * ================================================================== */

void SSCR_SynthNoteOn(uint8_t note, uint8_t velocity)
{
    printf("  NoteOn  note=%3u  vel=%3u\n", note, velocity);
}

void SSCR_SynthNoteOff(uint8_t note)
{
    printf("  NoteOff note=%3u\n", note);
}

/* ==================================================================
 * 包含播放器
 * ================================================================== */

#include "sscr_player.c"

/* ==================================================================
 * 主程序
 * ================================================================== */

int main(int argc, char** argv)
{
    if (argc < 2)
    {
        printf("Usage: %s <score.sscr>\n", argv[0]);
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

    /* 初始化 */
    SSCR_Player player;
    if (!SSCR_Init(&player, buf, (uint32_t)sz))
    {
        printf("Invalid SSCR file\n");
        free(buf);
        return 1;
    }

    printf("SSCR: transposition=%d  tickPerSecond=%u\n",
           SSCR_GetTotalTranspose(&player), player.tickPerSecond);

    /* Tick 驱动循环 */
    uint32_t tick = 0;
    while (!SSCR_IsFinished(&player))
    {
        SSCR_UpdateToTick(&player, tick);
        tick++;
    }

    printf("Finished at tick %u\n", tick);
    free(buf);
    return 0;
}
