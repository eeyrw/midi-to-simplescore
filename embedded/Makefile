# Makefile — 嵌入式 SSCR / SSPL 播放器
#
# 目标:
#   make single    — 编译单曲播放器示例
#   make playlist  — 编译多曲播放器示例
#   make all       — 编译全部
#   make clean
#
# 可覆盖变量:
#   CC      编译器 (默认 gcc)
#   CFLAGS  编译选项

CC      ?= gcc
CFLAGS  ?= -std=c99 -Wall -Wextra -Os

.PHONY: all single playlist clean

all: single playlist

single: example_single.c sscr_player.c
	$(CC) $(CFLAGS) -o example_single example_single.c

playlist: example_playlist.c sscr_player.c sspl_player.h
	$(CC) $(CFLAGS) -o example_playlist example_playlist.c

clean:
	rm -f example_single example_playlist
