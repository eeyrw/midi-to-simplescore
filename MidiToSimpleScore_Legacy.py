"""MIDI to SimpleScore Legacy — 旧格式（仅 NoteOn）转换器

输出 SSCR Legacy 格式（见 SSCR_LEGACY_SPEC.md）。

用法:
    python MidiToSimpleScore_Legacy.py song.mid -o score.bin
    python MidiToSimpleScore_Legacy.py song.mid --template template/generic/score.c.template

推荐新项目使用 SSCR 格式: MidiToSimpleScore.py --scoreFormat v3
"""

from __future__ import absolute_import
from mido import MidiFile
from functools import reduce
from io import StringIO
import os
import argparse
from string import Template


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
    noteOnList.append((mid.length, 128))
    return noteOnList


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

    try:
        from terminaltables import AsciiTable
        table = AsciiTable(tableData)
        table.inner_row_border = True
        table.title = 'Transpose'
        print(table.table)
    except ImportError:
        for row in tableData:
            print("{:<16} {}".format(*row))

    return suggestTranspose


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
        mem[-1] |= 0x80

    print("Mem size:", len(mem), "byte(s)")
    return mem


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
    scriptDir = os.path.dirname(os.path.abspath(__file__))
    if not os.path.isabs(templateFile):
        templateFile = os.path.join(scriptDir, templateFile)

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
        outputPath = os.path.join(outputDir,
                                  os.path.basename(os.path.splitext(templateFile)[0]))
        formatFileByParam(templateFile, outputPath, paramDict)


def main():
    noteNameValueMap = getNoteNameValueMap()

    parser = argparse.ArgumentParser(
        description='Legacy MIDI-to-SimpleScore converter (NoteOn only).')

    parser.add_argument('midi', type=str, help='MIDI file path.')
    parser.add_argument('--output', '-o', type=str, default='score.c',
                        help='Output file path.')
    parser.add_argument('--tickPerSecond', type=int, default=125,
                        help='Ticks per second on target device.')
    parser.add_argument('--voiceCenterNote', type=int,
                        default=noteNameValueMap['C:4'],
                        help='Center note of target voice (default C4=60).')
    parser.add_argument('--upperBoundNote', type=int, default=127,
                        help='Max MIDI note target device supports.')
    parser.add_argument('--lowerBoundNote', type=int, default=0,
                        help='Min MIDI note target device supports.')
    parser.add_argument('--transpose', type=int, default=None,
                        help='Override auto-calculated transpose.')
    parser.add_argument('--template', type=str, default=None,
                        help='Template file for C code generation.')
    args = parser.parse_args()

    noteOnList = readMidiFile(args.midi)
    centroidNote, lowestNote, highestNote = analyzeNoteList(noteOnList)

    if args.transpose is None:
        t = calcTranspose(centroidNote, lowestNote, highestNote,
                          args.voiceCenterNote,
                          args.lowerBoundNote,
                          args.upperBoundNote)
    else:
        t = args.transpose
        print('Manual transpose:', t)

    noteOnSetList = generateNoteOnSetList(noteOnList)
    binData = generateDeltaBin(noteOnSetList, args.tickPerSecond, t)

    if args.template:
        scoreMetaInfo = 'File: %s\n' % os.path.basename(args.midi)
        scoreMetaInfo += 'Transpose: %d' % t
        genCode([args.template], binData, scoreMetaInfo,
                os.path.dirname(os.path.abspath(args.output)))
    else:
        with open(args.output, 'wb') as f:
            f.write(binData)
        print('Raw binary written to', args.output)


if __name__ == "__main__":
    main()
