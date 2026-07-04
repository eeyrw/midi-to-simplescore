"""SSPL Packer — pack multiple MIDI files into a single SSPL container.

Usage:
    python SSPL_Packer.py song1.mid song2.mid ... -o playlist.sspl
"""

from __future__ import absolute_import
import struct
import os
import argparse

from MidiToSimpleScore import (
    readMidiFile, readMidiFileFull, analyzeNoteList,
    calcTranspose, calcEncodingTranspose,
    generateNoteOnSetList, generateDeltaBin,
    generateEventSetList, generateDeltaBinV3, addHeader,
)

SSPL_MAGIC = b'SSPL'
SSPL_VERSION = 0x01
SSPL_HEADER_SIZE = 12
SSPL_ENTRY_SIZE = 8
SSCR_HEADER_SIZE = 13


def build_sspl(midi_files, voiceCenterNote=60, lowerBoundNote=0,
               upperBoundNote=127, tickPerSecond=125,
               includeNoteOnVelocity=False, includeNoteOffVelocity=False):
    """Convert MIDI files to SSCR, pack into SSPL binary.

    Returns (sspl_bytes, entry_info_list).
    """

    sscr_blocks = []
    entry_info = []

    for path in midi_files:
        noteOnList = readMidiFile(path)
        centroid, lowest, highest = analyzeNoteList(noteOnList)
        voiceT = calcTranspose(centroid, lowest, highest,
                               voiceCenterNote, lowerBoundNote, upperBoundNote)
        encT, totalT = calcEncodingTranspose(centroid, lowest, highest,
                                             voiceT, lowerBoundNote, upperBoundNote)

        eventList = readMidiFileFull(path)
        eventSetList = generateEventSetList(eventList)
        raw = generateDeltaBinV3(eventSetList, tickPerSecond, totalT,
                                 includeNoteOnVelocity, includeNoteOffVelocity)
        sscr_data = addHeader(raw, tickPerSecond, totalT,
                              includeNoteOnVelocity, includeNoteOffVelocity)

        sscr_blocks.append(sscr_data)
        entry_info.append({
            'name': os.path.basename(path),
            'size': len(sscr_data),
        })

    data_start = SSPL_HEADER_SIZE + len(sscr_blocks) * SSPL_ENTRY_SIZE

    header = bytearray()
    header.extend(SSPL_MAGIC)
    header.append(SSPL_VERSION)
    header.append(0x00)  # Flags
    header += struct.pack('<H', len(sscr_blocks))
    header += struct.pack('<I', 0)  # Reserved

    table = bytearray()
    offset = data_start
    for i, blk in enumerate(sscr_blocks):
        table += struct.pack('<II', offset, len(blk))
        offset += len(blk)

    sspl = header + table
    for blk in sscr_blocks:
        sspl += blk

    return sspl, entry_info


def main():
    parser = argparse.ArgumentParser(
        description='Pack multiple MIDI files into SSPL container.')
    parser.add_argument('midi_files', nargs='+', help='MIDI files to pack')
    parser.add_argument('-o', '--output', default='playlist.sspl',
                        help='Output SSPL file path')
    parser.add_argument('--voiceCenterNote', type=int, default=60,
                        help='Center note of target voice (default C4=60)')
    parser.add_argument('--tickPerSecond', type=int, default=125)
    parser.add_argument('--includeNoteOnVelocity', action='store_true')
    parser.add_argument('--includeNoteOffVelocity', action='store_true')
    args = parser.parse_args()

    sspl_data, info = build_sspl(
        args.midi_files,
        voiceCenterNote=args.voiceCenterNote,
        tickPerSecond=args.tickPerSecond,
        includeNoteOnVelocity=args.includeNoteOnVelocity,
        includeNoteOffVelocity=args.includeNoteOffVelocity,
    )

    with open(args.output, 'wb') as f:
        f.write(sspl_data)

    total = sum(e['size'] for e in info)
    print(f"SSPL written: {args.output}")
    print(f"  Scores: {len(info)}")
    print(f"  Header + Table: {SSPL_HEADER_SIZE + len(info) * SSPL_ENTRY_SIZE} B")
    print(f"  SSCR data: {total} B")
    print(f"  Total: {len(sspl_data)} B")
    print()
    for i, e in enumerate(info):
        print(f"  [{i}] {e['name']}  ({e['size']} B)")


if __name__ == "__main__":
    main()
