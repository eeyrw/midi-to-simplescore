from __future__ import absolute_import
from os import read
from mido import MidiFile
from mido import tick2second
from functools import reduce
from io import StringIO
import os
from terminaltables import AsciiTable


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


def calcTranspose(centroidNote, lowestNote, highestNote, centerOfSuggest, lowerBoundPitch, upperBoundPitch):
    wantedTranspose = centerOfSuggest - centroidNote

    wantedHighestNote = highestNote + wantedTranspose
    wantedLowestNote = lowestNote + wantedTranspose

    suggestTranpose = wantedTranspose

    offestToValidHighestNote = upperBoundPitch - wantedHighestNote
    offestToValidLowestNote = lowerBoundPitch - wantedLowestNote

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
                 ('centerOfSuggest', str(centerOfSuggest)),
                 ('suggestTranpose', str(suggestTranpose)),
                 ]
    table = AsciiTable(tableData)
    table.inner_row_border = True
    table.title = 'Transpose'
    print(table.table)
    return suggestTranpose


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


noteNameValueMap = getNoteNameValueMap()
filePath = r"C:\Users\yuan\Desktop\midi-to-hex-example\midi-sample\piano_sonata_457_1_(c)oguri.mid"
noteOnList = readMidiFile(filePath)
centroidNote, lowestNote, highestNote = analyzeNoteList(noteOnList)
t = calcTranspose(centroidNote, lowestNote,
                  highestNote,noteNameValueMap['C:4'] , 0, 127)
noteOnSetList = generateNoteOnSetList(noteOnList)
bin = generateDeltaBin(noteOnSetList, 125, t)
print(getCStyleSampleDataString(bin, 16, '// %s' % os.path.basename(filePath)))
