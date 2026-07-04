"""MIDI to SimpleScore — SSCR / Legacy 乐谱转换器

将标准 MIDI 文件转换为嵌入式设备可播放的 SSCR 二进制格式。

用法:
    python MidiToSimpleScore.py --midi song.mid --outputDir ./output

格式:
    --scoreFormat v3    SSCR 格式（默认，推荐）
    --scoreFormat old   Legacy 格式（仅 NoteOn）

依赖: mido, terminaltables (可选)
"""

from __future__ import absolute_import
from os import read
from mido import MidiFile
from mido import tick2second
from functools import reduce
from io import StringIO
import os
try:
    from terminaltables import AsciiTable
except ImportError:
    AsciiTable = None
import argparse
try:
    from terminaltables import AsciiTable
except ImportError:
    AsciiTable = None
from string import Template


# ============================================================
# OLD FORMAT MIDI READER (note-on only)
# ============================================================

def readMidiFile(filePath):
    noteOnList = []
    mid = MidiFile(filePath)
    print('MIDI duration:', mid.length)
    absoluteTime = 0
    for msg in mid:
        absoluteTime += msg.time
        if msg.type == 'note_on' and msg.velocity != 0 and msg.channel != 9:
            noteOnList.append((absoluteTime, msg.note))

    noteOnList.sort(key=lambda x: x[0])
    noteOnList.append((mid.length, 128))  # End-of-midi tag

    return noteOnList


# ============================================================
# NEW FORMAT MIDI READER (note-on/off + velocity)
# ============================================================

def readMidiFileFull(filePath):
    eventList = []
    mid = MidiFile(filePath)

    absoluteTime = 0.0

    for msg in mid:
        absoluteTime += msg.time

        # 只处理音符消息
        if msg.type not in ('note_on', 'note_off'):
            continue

        # 跳过鼓轨 (channel 9)
        if msg.channel == 9:
            continue

        if msg.type == 'note_on':
            if msg.velocity != 0:
                eventList.append((absoluteTime, 1, msg.note, msg.velocity))
            else:
                eventList.append((absoluteTime, 0, msg.note, 0))

        elif msg.type == 'note_off':
            eventList.append((absoluteTime, 0, msg.note, 0))

    eventList.sort(key=lambda x: x[0])

    # End event - use mid.length for accurate duration
    eventList.append((mid.length, 2, 0, 0))

    return eventList



# ============================================================
# ANALYSIS (UNCHANGED)
# ============================================================

def analyzeNoteList(noteOnList):
    noteOccurtimeList = [0] * 128
    noteOnListWithoutEndTag = noteOnList[:-1]
    for _, note in noteOnListWithoutEndTag:
        noteOccurtimeList[note] += 1

    totalOccurrences = sum(noteOccurtimeList)
    if totalOccurrences == 0:
        return 0, 0, 0

    centroidNote = reduce(
        lambda x, y: x + y[0] * y[1], enumerate(noteOccurtimeList), 0
    ) // totalOccurrences

    noteOnlyList = [x[1] for x in noteOnListWithoutEndTag]
    return centroidNote, min(noteOnlyList), max(noteOnlyList)


def getNoteNameValueMap():
    pitchInOneOctave = ("C", "C#", "D", "Eb", "E", "F",
                        "F#", "G", "Ab", "A", "Bb", "B")
    noteNameValueMap = {}
    for midiNote in range(128):
        octaveGroup = (midiNote - 12) // 12
        pitch = abs((midiNote - 12) % 12)
        noteNameValueMap[pitchInOneOctave[pitch] +
                         ":" + str(octaveGroup)] = midiNote
    return noteNameValueMap


# ============================================================
# TRANSPOSE (UNCHANGED)
# ============================================================

def calcTranspose(centroidNote, lowestNote, highestNote,
                  voiceCenterNote, lowerBoundNote, upperBoundNote):

    suggestTranspose = voiceCenterNote - centroidNote

    afterTransposeHighest = highestNote + suggestTranspose
    afterTransposeLowest = lowestNote + suggestTranspose

    offsetToValidHighest = upperBoundNote - afterTransposeHighest
    offsetToValidLowest = lowerBoundNote - afterTransposeLowest

    if offsetToValidHighest >= 0 and offsetToValidLowest <= 0:
        pass
    elif offsetToValidHighest < 0 and offsetToValidLowest > 0:
        if abs(offsetToValidHighest) <= abs(offsetToValidLowest):
            suggestTranspose += offsetToValidHighest
        else:
            suggestTranspose += offsetToValidLowest
    elif offsetToValidHighest < 0:
        suggestTranspose += offsetToValidHighest
    elif offsetToValidLowest > 0:
        suggestTranspose += offsetToValidLowest

    tableData = [('Item', 'Value'),
                 ('lowestNote', str(lowestNote)),
                 ('highestNote', str(highestNote)),
                 ('centroidNote', str(centroidNote)),
                 ('voiceCenterNote', str(voiceCenterNote)),
                 ('suggestTranspose', str(suggestTranspose)),
                 ]

    if AsciiTable is not None:
        table = AsciiTable(tableData)
        table.inner_row_border = True
        table.title = 'Transpose'
        tableText = table.table
    else:
        lines = ["{:<18} {}".format(*row) for row in tableData]
        tableText = '\n'.join(lines)

    return suggestTranspose, tableText


# ============================================================
# OLD FORMAT GENERATOR
# ============================================================

def generateNoteOnSetList(noteOnList):
    lastTime = -1
    lastIndex = -1
    noteOnSetList = []
    for noteItem in noteOnList:
        if abs(noteItem[0] - lastTime) < 1e-3:
            lastTime = noteItem[0]
            noteOnSetList[lastIndex][1].append(noteItem[1])
        else:
            lastTime = noteItem[0]
            lastIndex += 1
            noteOnSetList.append((noteItem[0], [noteItem[1]]))
    return noteOnSetList


def generateDeltaBin(noteOnSetList, tickPerSecond, transpose=0):
    lastTick = 0
    mem = bytearray()
    for noteOnSetItem in noteOnSetList:
        currentTick = int(noteOnSetItem[0] * tickPerSecond)
        deltaTick = currentTick - lastTick
        lastTick = currentTick

        while True:
            t = deltaTick if deltaTick < 255 else 255
            mem.append(t)
            deltaTick -= 255
            if deltaTick < 0:
                break

        for note in noteOnSetItem[1]:
            if note == 128:
                mem.append(0xFF)
            else:
                mem.append((note + transpose) & 0x7F)
        mem[-1] |= 128

    print("Mem size (OLD): ", len(mem), " byte(s)")
    return mem


# ============================================================
# EVENT GROUPING (shared by V3)
# ============================================================

def generateEventSetList(eventList):
    lastTime = -1
    lastIndex = -1
    eventSetList = []

    for event in eventList:
        time = event[0]

        if abs(time - lastTime) < 1e-3:
            eventSetList[lastIndex][1].append(event[1:])
        else:
            lastTime = time
            lastIndex += 1
            eventSetList.append((time, [event[1:]]))

    return eventSetList


# ============================================================
# SSCR FORMAT GENERATOR
# ============================================================

def writeDeltaV3(value):
    """6-bit little-endian delta with bit6 continuation"""
    out = []
    while True:
        byte = value & 0x3F
        value >>= 6
        if value:
            byte |= 0x40
        out.append(byte)
        if not value:
            break
    return out

def encodeEventV3(eventType, note, velocity, includeNoteOnVelocity, includeNoteOffVelocity):
    """Encode a single event into V3 bytes"""
    out = bytearray()
    isExtended = note > 61

    if eventType == 1:  # NoteOn
        if isExtended:
            out.append(0xFF)
            out.append(note & 0x7F)
        else:
            out.append(0xC0 | note)
        if includeNoteOnVelocity:
            out.append(velocity & 0x7F)
    elif eventType == 0:  # NoteOff
        if isExtended:
            out.append(0xBF)
            out.append(note & 0x7F)
        else:
            out.append(0x80 | note)
        if includeNoteOffVelocity:
            out.append(velocity & 0x7F)
    # EndOfScore (type 2) handled separately

    return out

def generateDeltaBinV3(eventSetList, tickPerSecond, transpose=0,
                       includeNoteOnVelocity=False, includeNoteOffVelocity=False):
    lastTick = 0
    mem = bytearray()

    for i, eventSetItem in enumerate(eventSetList):
        currentTick = int(eventSetItem[0] * tickPerSecond)
        deltaTick = currentTick - lastTick
        lastTick = currentTick

        mem.extend(writeDeltaV3(deltaTick))

        for event in eventSetItem[1]:
            eventType, note, velocity = event

            if eventType == 2:  # EndOfScore
                continue

            mem.extend(encodeEventV3(
                eventType, (note + transpose) & 0x7F, velocity,
                includeNoteOnVelocity, includeNoteOffVelocity))

    # Append EndOfScore: delta=0 + EOS
    mem.extend(writeDeltaV3(0))
    mem.append(0xBE)

    print("Mem size (V3):", len(mem), " byte(s)")
    return mem

def addHeader(scoreBytes, tickPerSecond, includeNoteOnVelocity=False, includeNoteOffVelocity=False):
    header = bytearray()
    header.extend(b'SSCR')
    header.append(0x02)  # Version 2 = V3 format

    flags = 0
    if includeNoteOnVelocity:
        flags |= 0x01
    if includeNoteOffVelocity:
        flags |= 0x02
    header.append(flags)

    header.append(tickPerSecond & 0xFF)
    header.append((tickPerSecond >> 8) & 0xFF)

    length = len(scoreBytes)
    header.append(length & 0xFF)
    header.append((length >> 8) & 0xFF)
    header.append((length >> 16) & 0xFF)
    header.append((length >> 24) & 0xFF)

    print("Header added. Total size:", len(header) + len(scoreBytes))
    return header + scoreBytes


# ============================================================
# COMMON OUTPUT
# ============================================================

def getCStyleSampleDataString(sampleArray, colWidth, dataDescription=''):
    file_str = StringIO()
    newLineCounter = 0
    file_str.write(dataDescription + '\n')
    for sample in sampleArray:
        file_str.write("0x%02x," % sample)
        if newLineCounter > colWidth:
            newLineCounter = 0
            file_str.write("\n")
        else:
            newLineCounter += 1
    return file_str.getvalue()


def formatFileByParam(templateFile, outputFile, param):
    with open(templateFile, 'r') as tmplFile:
        tmplString = tmplFile.read()
        s = Template(tmplString)
        with open(outputFile, 'w') as outFile:
            outFile.write(s.safe_substitute(param))


def genCode(templateFiles, scoreBytes, scoreMetaInfo, outputDir):
    scoreBytesDataString = getCStyleSampleDataString(
        scoreBytes, 16, dataDescription='')

    paramDict = {}
    paramDict['ScoreDataLen'] = len(scoreBytes)
    paramDict['ScoreMetaInfo'] = scoreMetaInfo
    paramDict['ScoreData'] = scoreBytesDataString

    for templateFile in templateFiles:
        formatFileByParam(templateFile,
                          os.path.join(outputDir,
                                       os.path.basename(os.path.splitext(
                                           templateFile)[0])),
                          paramDict)


# ============================================================
# MAIN
# ============================================================

def main():
    noteNameValueMap = getNoteNameValueMap()

    parser = argparse.ArgumentParser(
        description='The midi to simple score converting tool.')

    parser.add_argument('--midi', type=str, required=True,
                        help='midi file path.')

    parser.add_argument('--useExtraTranspose', default=False,
                        action='store_true',
                        help='Use user specific tranpose value.')

    parser.add_argument('--transpose', type=int, default=0,
                        help='Transpose in half note.')

    parser.add_argument('--upperBoundNote', type=int, default=127,
                        help='Max midi note which target device can support.')

    parser.add_argument('--lowerBoundNote', type=int, default=0,
                        help='Min midi note which target device can support.')

    parser.add_argument('--voiceCenterNote', type=int,
                        default=noteNameValueMap['C:4'],
                        help='Center note of target voice.')

    parser.add_argument('--tickPerSecond', type=int, default=125,
                        help='Ticks per second on target device.')

    parser.add_argument('--outputDir', type=str, default='.',
                        help='Output directory.')

    parser.add_argument('--template', type=str, default='8051_sdcc',
                        help='Using interal template by specifing type.')

    parser.add_argument('--extraTemplate', nargs='+', type=str, default=[],
                        help='Using extra template files.')

    parser.add_argument('--scoreFormat', type=str, default='v3',
                        choices=['old', 'v3'],
                        help='Score format: old (legacy) or v3 (recommended).')
    parser.add_argument('--includeNoteOnVelocity', default=False,
                        action='store_true',
                        help='Store velocity for NoteOn events')
    parser.add_argument('--includeNoteOffVelocity', default=False,
                        action='store_true',
                        help='Store velocity for NoteOff events')
    args = parser.parse_args()

    # Template selection
    if args.template is not None:
        templateFileList = []
        scriptDir = os.path.dirname(os.path.abspath(__file__))
        templateDir = os.path.join(scriptDir, 'template', args.template)
        for filePath in os.listdir(templateDir):
            if os.path.splitext(filePath)[1] == '.template':
                templateFileList.append(
                    os.path.join(templateDir, filePath))
    else:
        templateFileList = args.extraTemplate

    filePath = args.midi

    # Analyze based on old note-on list
    noteOnList = readMidiFile(filePath)
    centroidNote, lowestNote, highestNote = analyzeNoteList(noteOnList)

    if not args.useExtraTranspose:
        t, transposeMetaInfo = calcTranspose(
            centroidNote, lowestNote, highestNote,
            args.voiceCenterNote,
            args.lowerBoundNote,
            args.upperBoundNote)
    else:
        t = args.transpose
        transposeMetaInfo = 'Use Extern Transpose: %d' % t

    # Generate score
    if args.scoreFormat == 'old':
        noteOnSetList = generateNoteOnSetList(noteOnList)
        binData = generateDeltaBin(noteOnSetList,
                                   args.tickPerSecond, t)
    else:
        eventList = readMidiFileFull(filePath)
        eventSetList = generateEventSetList(eventList)
        raw = generateDeltaBinV3(eventSetList,
                                 args.tickPerSecond, t,
                                 args.includeNoteOnVelocity,
                                 args.includeNoteOffVelocity)
        binData = addHeader(raw, args.tickPerSecond,
                            args.includeNoteOnVelocity,
                            args.includeNoteOffVelocity)

    scoreMetaInfo = 'File: %s\n' % os.path.basename(filePath)
    scoreMetaInfo += transposeMetaInfo

    genCode(templateFileList, binData, scoreMetaInfo, args.outputDir)


if __name__ == "__main__":
    main()
