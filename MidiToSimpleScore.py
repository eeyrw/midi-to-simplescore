from __future__ import absolute_import
from os import read
from mido import MidiFile
from mido import tick2second
from functools import reduce
from io import StringIO
import os
from terminaltables import AsciiTable
import argparse
from gooey import Gooey
from gooey import GooeyParser
from string import Template


def readMidiFile(filePath):
    noteOnList = []
    mid = MidiFile(filePath)
    print('MIDI duration:', mid.length)
    absoluteTime = 0
    for msg in mid:
        absoluteTime += msg.time
        if msg.type == 'note_on' and msg.velocity is not 0 and msg.channel is not 9:
            noteOnList.append((absoluteTime, msg.note))

    noteOnList.sort(key=lambda x: x[0])
    noteOnList.append((mid.length, 128))  # Add End-of-midi tag

    return noteOnList


def analyzeNoteList(noteOnList):
    noteOccurtimeList = [0]*128
    noteOnListWithoutEndTag = noteOnList[:-1]
    for _, note in noteOnListWithoutEndTag:
        noteOccurtimeList[note] += 1

    centroidNote = reduce(
        lambda x, y: x+y[0]*y[1], enumerate(noteOccurtimeList), 0) // sum(noteOccurtimeList)
    noteOnlyList = [x[1] for x in noteOnListWithoutEndTag]
    return centroidNote, min(noteOnlyList), max(noteOnlyList)


def getNoteNameValueMap():
    pitchInOneOctave = ("C", "C#", "D", "Eb", "E", "F",
                        "F#", "G", "Ab", "A", "Bb", "B")
    noteNameValueMap = {}
    # Midi pitch 12=C0,108=C8
    for midiNote in range(128):
        octaveGroup = (midiNote - 12) // 12
        pitch = abs((midiNote - 12) % 12)
        noteNameValueMap[pitchInOneOctave[pitch] +
                         ":" + str(octaveGroup)] = midiNote
    return noteNameValueMap


def calcTranspose(centroidNote, lowestNote, highestNote, voiceCenterNote, lowerBoundNote, upperBoundNote):
    wantedTranspose = voiceCenterNote - centroidNote

    wantedHighestNote = highestNote + wantedTranspose
    wantedLowestNote = lowestNote + wantedTranspose

    suggestTranpose = wantedTranspose

    offestToValidHighestNote = upperBoundNote - wantedHighestNote
    offestToValidLowestNote = lowerBoundNote - wantedLowestNote

    if offestToValidHighestNote >= 0 and offestToValidLowestNote <= 0:
        suggestTranpose += 0
    elif offestToValidHighestNote < 0:
        # keep the highest pitch by all means
        suggestTranpose += offestToValidHighestNote
    elif offestToValidLowestNote >= 0:
        if abs(offestToValidHighestNote) >= abs(offestToValidLowestNote):
            suggestTranpose += offestToValidLowestNote
        else:
            suggestTranpose += offestToValidHighestNote

    tableData = [('Item', 'Value'),
                 ('lowestNote', str(lowestNote)),
                 ('highestNote', str(highestNote)),
                 ('centroidNote', str(centroidNote)),
                 ('voiceCenterNote', str(voiceCenterNote)),
                 ('suggestTranpose', str(suggestTranpose)),
                 ]
    table = AsciiTable(tableData)
    table.inner_row_border = True
    table.title = 'Transpose'
    return suggestTranpose, table.table


def generateNoteOnSetList(noteOnList):
    lastTime = -1
    lastIndex = -1
    noteOnSetList = []
    for noteItem in noteOnList:
        if abs(noteItem[0]-lastTime) < 1e-3:
            lastTime = noteItem[0]
            noteOnSetList[lastIndex][1].append(noteItem[1])
        else:
            lastTime = noteItem[0]
            lastIndex += 1
            noteOnSetList.append((noteItem[0], [noteItem[1]]))
    return noteOnSetList


def getCStyleSampleDataString(sampleArray, colWidth, dataDescription=''):
    file_str = StringIO()
    newLineCounter = 0
    file_str.write(dataDescription+'\n')
    for sample in sampleArray:
        file_str.write("0x%02x," % sample)
        if newLineCounter > colWidth:
            newLineCounter = 0
            file_str.write("\n")
        else:
            newLineCounter += 1
    return file_str.getvalue()


def generateDeltaBin(noteOnSetList, tickPerSecond, transpose=0):
    lastTick = 0
    mem = bytearray()
    for noteOnSetItem in noteOnSetList:
        currentTick = int(noteOnSetItem[0]*tickPerSecond)
        deltaTick = currentTick - lastTick
        lastTick = currentTick
        while True:
            if deltaTick < 255:
                t = deltaTick
            else:
                t = 255
            mem.append(t)
            deltaTick -= 255
            if deltaTick < 0:
                break

        for note in noteOnSetItem[1]:
            if note == 128:
                mem.append(0xFF)
            else:
                mem.append(note+transpose)
        mem[-1] |= 128

    print("Mem size: ", len(mem), " byte(s)")
    return mem


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
        formatFileByParam(templateFile, os.path.join(outputDir, os.path.basename(os.path.splitext(
            templateFile)[0])), paramDict)


@Gooey
def main():
    noteNameValueMap = getNoteNameValueMap()
    parser = GooeyParser(
        description='The midi to simple score converting tool.')
    # parser = argparse.ArgumentParser(
    #     description='The midi to simple score converting tool.')
    parser.add_argument('--midi', type=str, default=r"C:\Users\yuan\Desktop\midi-to-hex-example\midi-sample\Mozart_314_Allegro.mid",
                        help='midi file path.', widget='FileChooser')
    parser.add_argument('--useExtraTranspose', default=False, action='store_true',
                        help='Use user specific tranpose value by param transpose.')
    parser.add_argument('--transpose', type=int, default=0,
                        help='Transpose in half note.')
    parser.add_argument('--upperBoundNote', type=int, default=127,
                        help='Max midi note which target device can support.')
    parser.add_argument('--lowerBoundNote', type=int, default=0,
                        help='Min midi note which target device can support.')
    parser.add_argument('--voiceCenterNote', type=int, default=noteNameValueMap['C:4'],
                        help='Center note of target voice. P.S: C4=60')
    parser.add_argument('--tickPerSecond', type=int, default=125,
                        help='Ticks per second on target device.')
    parser.add_argument('--outputDir', type=str, default='.',
                        help='Output directory.', widget='DirChooser')
    parser.add_argument('--template', type=str, default='8051_sdcc',
                        help='Using interal template by specifing type.')
    parser.add_argument('--extraTemplate', nargs='+', type=str, default=[],
                        help='Using extra template files instead of self-contained template.')
    args = parser.parse_args()

    if args.template != None:
        templateFileList = []
        for filePath in os.listdir(os.path.join('./template', args.template)):
            if os.path.splitext(filePath)[1] == '.template':
                templateFileList.append(os.path.join(
                    './template', args.template, filePath))
    else:
        templateFileList = args.extraTemplate

    filePath = args.midi
    noteOnList = readMidiFile(filePath)
    centroidNote, lowestNote, highestNote = analyzeNoteList(noteOnList)
    if not args.useExtraTranspose:
        t, transposeMetaInfo = calcTranspose(centroidNote, lowestNote,
                                             highestNote, args.voiceCenterNote, args.lowerBoundNote, args.upperBoundNote)
    else:
        t = args.transpose
        transposeMetaInfo = 'Use Extern Transpose: %d' % t
    noteOnSetList = generateNoteOnSetList(noteOnList)
    bin = generateDeltaBin(noteOnSetList, args.tickPerSecond, t)

    scoreMetaInfo = 'File: %s\n' % os.path.basename(filePath)
    scoreMetaInfo += transposeMetaInfo

    genCode(templateFileList, bin, scoreMetaInfo, args.outputDir)


if __name__ == "__main__":
    main()
