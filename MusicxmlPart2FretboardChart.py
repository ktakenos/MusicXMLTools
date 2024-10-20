# -*- coding: utf-8 -*-
"""
Created on Fri Dec 30 20:37:18 2022

@author: ktakenos@gmail.com

https://gis.stackexchange.com/questions/58271/using-python-to-parse-an-xml-containing-gml-tags
https://www.pythontutorial.net/python-concurrency/python-thread-queue/
https://watlab-blog.com/2024/06/15/threading-realtime-fft/

"""
import tkinter as Tk
from tkinter import filedialog
from tkinter.colorchooser import askcolor
import subprocess
import re
import xml.etree.ElementTree as ET
from PIL import Image, ImageTk
from PIL import ImageDraw
from PIL import ImageFont
from pathlib import Path
import time
import pygame
import scipy.io.wavfile as wavefile
import numpy as np
from scipy import signal
import math
from queue import Empty, Queue
from threading import Thread

root = Tk.Tk()
root.title('Music XML Conversion Tool: Fretboard Chart to mp4')

InputFileName=''
fFileLoaded = 0
ttfontname = "c:\\Windows\\Fonts\\meiryob.ttc"
fontsize = 16
Width = 1280
Height = 360
TextImageW = 30
TextImageH = 20
MainCanvasSize = (Width, Height)
backgroundRGB = [140,100,64, 255]
textRGB = [128,255,255,255]
fFretboardInitialized =0
# semitones of openstrings
# E4=12*4+4-8, B3=12*3+11-8, G3=12*3+7-8, D3=12*3+2-8, A2=12*2+9-8, E2=12*2+4-8
OpenStrings=[44, 39, 35, 30, 25, 20]
notes = []
maxNotes = 0
maxMeasures = 0
fFileLoaded = 0

TempoSong = 120
samplerate = 44100
Volume = 0.3
WaveData = None
SynthA4Wave = np.zeros(samplerate*2, dtype=np.int16)
for i in range(samplerate*2):
    t = 1/float(samplerate)*float(i)
    A = pow(2, 14)
    SynthA4Wave[i] = A * np.sin(2*np.pi*440.0*t)
SynthA5Wave = np.zeros(samplerate*2, dtype=np.int16)
for i in range(samplerate*2):
    t = 1/float(samplerate)*float(i)
    A = pow(2, 11)
    SynthA5Wave[i] = A * np.sin(2*np.pi*880.0*t) \
        + A*0.6 * np.sin(2*np.pi*1760.0*t) + A*0.9 * np.sin(2*np.pi*2640.0*t) \
        + A*0.5 * np.sin(2*np.pi*3520.0*t) + A*0.8 * np.sin(2*np.pi*6160.0*t) \
        + A*0.4 * np.sin(2*np.pi*5280.0*t) + A*0.7 * np.sin(2*np.pi*3520.0*t) \
        + A*0.3 * np.sin(2*np.pi*7040.0*t) + A*0.6 * np.sin(2*np.pi*7920.0*t)
Tick0Wave = np.zeros(int(float(samplerate)*0.05), dtype=np.int16)
for i in range(int(float(samplerate)*0.05)):
    t = 1/float(samplerate)*float(i)
    A = pow(2, 12)
    Tick0Wave[i] = A*1.5 * np.sin(2*np.pi*3520.0*t) \
        + A*1.5 * np.sin(2*np.pi*7040.0*t) + A*0.4 * np.sin(2*np.pi*10560.0*t) \
        + A*1.5 * np.sin(2*np.pi*14080.0*t) + A*0.4 * np.sin(2*np.pi*1760.0*t)
Tick1Wave = np.zeros(int(float(samplerate)*0.05), dtype=np.int16)
for i in range(int(float(samplerate)*0.05)):
    t = 1/float(samplerate)*float(i)
    A = pow(2, 11)
    Tick1Wave[i] = A * np.sin(2*np.pi*1760.0*t) \
        + A*0.2 * np.sin(2*np.pi*3520.0*t) + A*1.5 * np.sin(2*np.pi*5280.0*t) \
        + A*0.2 * np.sin(2*np.pi*7040.0*t) + A*1.5 * np.sin(2*np.pi*8800.0*t)
idxFrame = 0
fps = 30
maxSeconds = 90
fShowNote = 1
fSource = 0
fPlayNotes = 0
idxPlayNotes = 0
idxNotePlayed = 0
idxSectionFrom = 0
idxSectionTo = 0
TempoPlayNotes = 120

fWindowClose = 0

def LoadFile():
    global InputFileName, fFileLoaded
    filetypes = (("Music XML", "*.musicxml"),('All files', '*.*'))
    InputFileName = filedialog.askopenfilename(initialdir='./', filetypes=filetypes)
    LoadNotes()
    if(fFileLoaded==1):
        FileEntry.delete(0, Tk.END)
        FileEntry.insert(0, InputFileName)
        InitializeFretboard()
LoadButton = Tk.Button(root, text='Clic to Read Music XML File', width=25, command=LoadFile)
LoadButton.grid(row=0, column=0, columnspan=2, sticky=Tk.W+Tk.E)

FileEntry = Tk.Entry(root, width=80, justify='left')
FileEntry.insert(0, 'No Music XML file is Loaded')
FileEntry.grid(row=0, column=2, columnspan=6, sticky=Tk.W+Tk.E, ipadx=0, padx=0)

MainImg = Image.new('RGBA', MainCanvasSize, tuple(backgroundRGB))
MainDraw = ImageDraw.Draw(MainImg)
FretImg = MainImg.copy()
font = ImageFont.truetype(ttfontname, fontsize)
TextCanvasSize= (TextImageW, TextImageH)
TextImg = Image.new('RGBA', TextCanvasSize, (255,255,255,0))
TextDraw = ImageDraw.Draw(TextImg)

ImageLabel = Tk.Label(root)
ImageLabel.grid(row=1, column=0, columnspan=10, sticky=Tk.NW+Tk.SE)
Disp_img = MainImg.resize((int(Width/2),int(Height/2)))
imgtk = ImageTk.PhotoImage(image=Disp_img)
ImageLabel.imgtk = imgtk
ImageLabel.configure(image=imgtk)

def getLengthOfNote(text):
    value = 0.0
    if(text == 'whole'):
        value = 1.0
    elif(text == 'half'):
        value = 1/2.0
    elif(text == 'quarter'):
        value = 1/4.0
    elif(text == 'eighth'):
        value = 1/8.0
    elif(text == '16th'):
        value = 1/16.0
    elif(text == '32nd'):
        value = 1/32.0
    elif(text == '64th'):
        value = 1/64.0
    return value

def getSemitoneNumber(step, octave, alter):
    value = 0    
    if(step == 'C'):
        value = 0
    elif(step == 'D'):
        value = 2
    elif(step == 'E'):
        value = 4
    elif(step == 'F'):
        value = 5
    elif(step == 'G'):
        value = 7
    elif(step == 'A'):
        value = 9
    elif(step == 'B'):
        value = 11
    value = int(value) + 12 * int(octave) + int(alter)
    # A0 is semitone #1
    return value - 8

def LoadNotes():
    global InputFileName, fFileLoaded, Lyrics, Seconds, TonePitch, Beats, notes, maxNotes, maxMeasures, TempoSong, TempoPlayNotes, idxSectionTo
    if(fFileLoaded == 1):
        notes = []
        maxNotes = 0
    if(InputFileName!=''):
        if(maxNotes>0):
            maxNotes = 0
        tree = ET.parse(InputFileName)
        root = tree.getroot()
        for tempo in root.iter(tag="sound"):
            if('tempo' in tempo.attrib):
                tempoText = "%s" % tempo.attrib
                tempoValue = float(re.findall('[0-9]+', tempoText.split()[1])[0])
                TempoSong = tempoValue
                TempoPlayNotes = tempoValue
                TempoLabel.configure(text='Tempo: %d' % int(TempoPlayNotes))
        sec0 = 0
        sec1 = 0
        idxMeasure = 0
        idxNote = 0
        Measures = 0.0
        fracMeasure = 0.0
        sec0 = 0
        sec1 = 0
        for measure in root.iter('measure'):
            Measures = float(idxMeasure)
            fracMeasure %=1.0
            for note in measure.iter(tag='note'):
                # sec0 = sec1
                NoteString=''
                if(note.find('pitch') != None):
                    step = note.find('pitch/step')
                    octave = note.find('pitch/octave')
                    alter=note.find("pitch/alter")
                    alterValue=0
                    #Determin the note semitone
                    if(step != None):
                        NoteString += step.text
                        NoteString += octave.text
                        if(alter != None):
                            if(alter.text == '1'):
                                NoteString += '♯'
                                alterValue=1
                            elif(alter.text == '-1'):
                                NoteString += '♭'
                                alterValue=-1
                    Semitone = getSemitoneNumber(step.text  , octave.text , alterValue)
                    #Determin the note length
                    length = note.find("type")
                    NoteLength = float(getLengthOfNote(length.text))
                    dot = note.find("dot")
                    if(dot != None):
                        NoteLength *= 1.5
                    modification = note.find('time-modification')
                    if(modification != None):
                        Actual = modification.find('actual-notes')
                        Normal = modification.find('normal-notes')
                        NoteLength *= float(Normal.text)/float(Actual.text)
                    #Check if note in chord
                    fChord = 0
                    chord = note.find("chord")
                    if(chord != None):
                        fChord = 1
                    #Check if note is tied ended
                    fTieEnd = 0
                    Tie = note.find('tie')
                    if(Tie != None):
                       if('stop' in Tie.attrib['type']):
                           fTieEnd = 1
                    #Store note in list
                    if((fChord==0)&(fTieEnd==0)):
                        #Measure to be progressed
                        # Measures = float(idxMeasure)+fracMeasure
                        # NoteEndMeasures = Measures + NoteLength
                        sec0 = Measures * 60.0/tempoValue*4.0
                        sec1 = sec0 + NoteLength * 60.0/tempoValue*4.0
                        #notes List format [ 0:Measures from, 1:note length, 2:sec from, 3:sec end, 4:semitone list]
                        notes.append(('%8.4f' % float(Measures), '%6.4f' % float(NoteLength), sec0, sec1, [Semitone]))
                        Measures += NoteLength
                        idxNote += 1
                    elif(fChord == 1):
                        if(Semitone not in notes[idxNote-1][4]):
                            notes[idxNote-1][4].append(Semitone)
                    elif(fTieEnd):
                        PrevList = list(notes[idxNote-1])
                        PrevList[1] = float(PrevList[1]) + float(NoteLength)
                        PrevList[3] = float(PrevList[3]) + float(NoteLength) * 60.0/tempoValue*4.0
                        notes[idxNote-1] = (PrevList[0], PrevList[1], PrevList[2], PrevList[3], PrevList[4]) 
                        Measures += NoteLength
                elif(note.find('rest') != None):
                    NoteString+='Rest'
                    length = note.find("type")
                    NoteLength = float(getLengthOfNote(length.text))
                    modification = note.find('time-modification')
                    if(modification != None):
                        Actual = modification.find('actual-notes')
                        Normal = modification.find('normal-notes')
                        NoteLength *= float(Normal.text)/float(Actual.text)
                    # NoteEndMeasures = Measures + NoteLength
                    sec0 = Measures * 60.0/tempoValue*4.0
                    # sec1 = NoteEndMeasures * 60.0/tempoValue*4.0
                    sec1 = sec0 + NoteLength * 60.0/tempoValue*4.0
                    notes.append(('%8.4f' % float(Measures), '%6.4f' % float(NoteLength), sec0, sec1, ['']))
                    Measures += NoteLength
                    idxNote += 1
            idxMeasure +=1
        maxNotes=len(notes)
        idxSectionTo = maxNotes-1
        maxMeasures = idxMeasure-1
        SectionToLabel.configure(text='%d' % maxMeasures)
        FrameScale.configure(to=maxNotes)
        FrameScale.set(0)
        MaxTEntry.delete(0, 'end')
        MaxTEntry.insert(0, int(sec1))
        fFileLoaded = 1
    
FrameTitleLabel = Tk.Label(root, text='Fretboard Chart Frame Format', width=20)
FrameTitleLabel.grid(row=2, column=0, columnspan=8, sticky=Tk.W+Tk.E, ipadx=0)
SizeLabel = Tk.Label(root, text='Frame Width x Height', width=15)
SizeLabel.grid(row=3, column=0, columnspan=2, sticky=Tk.W+Tk.E, ipadx=0)
WidthEntry = Tk.Entry(root, width=5, justify='center')
WidthEntry.insert(0, '1280')
WidthEntry.grid(row=3, column=2, sticky=Tk.W+Tk.E, ipadx=0, padx=0)
CrossLabel = Tk.Label(root, text=' x ', width=5, justify='center')
CrossLabel.grid(row=3, column=3, sticky=Tk.W+Tk.E, ipadx=0)
HeightEntry = Tk.Entry(root, width=5, justify='center')
HeightEntry.insert(0, '360')
HeightEntry.grid(row=3, column=4, sticky=Tk.W+Tk.E, ipadx=0, padx=0)
BGLabel = Tk.Label(root, text='Background color', width=5, justify='center')
BGLabel.grid(row=3, column=6, sticky=Tk.W+Tk.E, ipadx=0)
def BackgroundColorChooser():
    global backgroundRGB, Width, Height, MainCanvasSize, MainImg, backgroundRGB
    colors=askcolor('#%02x%02x%02x' % (backgroundRGB[0],backgroundRGB[1],backgroundRGB[2]), title='Choose Background Color')
    backgroundRGB[0] = colors[0][0]
    backgroundRGB[1] = colors[0][1]
    backgroundRGB[2] = colors[0][2]
    BGColorButton.configure(bg=colors[1])
    Width = int(WidthEntry.get())
    Height = int(HeightEntry.get())
    MainCanvasSize = (Width, Height)
    MainImg = Image.new('RGBA', MainCanvasSize, tuple(backgroundRGB))
    MainDraw = ImageDraw.Draw(MainImg)
    MainDraw.rectangle((0,0, Width, Height), fill=tuple(backgroundRGB))
    Disp_img = MainImg.resize((int(Width/2),int(Height/2)))
    imgtk = ImageTk.PhotoImage(image=Disp_img)
    ImageLabel.imgtk = imgtk
    ImageLabel.configure(image=imgtk)
BGColorButton=Tk.Button(root, text='Color', bg='#AC6440',  command=BackgroundColorChooser)
BGColorButton.grid(row=3, column=7, sticky=Tk.W+Tk.E)

SizeLabel = Tk.Label(root, text='Note Text size and Font size', width=15)
SizeLabel.grid(row=4, column=0, columnspan=2, sticky=Tk.W+Tk.E, ipadx=0)
TextWidthEntry = Tk.Entry(root, width=5, justify='center')
TextWidthEntry.insert(0, '120')
TextWidthEntry.grid(row=4, column=2, sticky=Tk.W+Tk.E, ipadx=0, padx=0)
TextCrossLabel = Tk.Label(root, text=' x ', width=5, justify='center')
TextCrossLabel.grid(row=4, column=3, sticky=Tk.W+Tk.E, ipadx=0)
TextHeightEntry = Tk.Entry(root, width=5, justify='center')
TextHeightEntry.insert(0, '40')
TextHeightEntry.grid(row=4, column=4, sticky=Tk.W+Tk.E, ipadx=0, padx=0)
TextSizeLabel = Tk.Label(root, text='Font size [pt]', width=8)
TextSizeLabel.grid(row=3, column=5, sticky=Tk.W+Tk.E, ipadx=0)
TextSizeEntry = Tk.Entry(root, width=5, justify='center')
TextSizeEntry.insert(0, '34')
TextSizeEntry.grid(row=4, column=5, ipadx=0, padx=0)
TextColorLabel = Tk.Label(root, text='Font Color', width=10)
TextColorLabel.grid(row=4, column=6, sticky=Tk.W+Tk.E, ipadx=0)
def FontColorChooser():
    global textRGB
    colors=askcolor('#%02x%02x%02x' % (textRGB[0],textRGB[1],textRGB[2]), title='Choose Font Color')
    textRGB[0] = colors[0][0]
    textRGB[1] = colors[0][1]
    textRGB[2] = colors[0][2]
    FontColorButton.configure(bg=colors[1])
FontColorButton=Tk.Button(root, text='Color', bg='#A0FFFF',  command=FontColorChooser)
FontColorButton.grid(row=4, column=7, sticky=Tk.W+Tk.E)
VideoLabel = Tk.Label(root, text='Video Max. Length t[sec]=', width=15)
VideoLabel.grid(row=5, column=0, columnspan=2, sticky=Tk.W+Tk.E, ipadx=0)
MaxTEntry = Tk.Entry(root, width=5, justify='center')
MaxTEntry.insert(0, '90')
MaxTEntry.grid(row=5, column=2, sticky=Tk.W+Tk.E, ipadx=0, padx=0)
FPSLabel = Tk.Label(root, text='FPS=', width=5, justify='right')
FPSLabel.grid(row=5, column=3, sticky=Tk.W+Tk.E, ipadx=0)
FPSEntry = Tk.Entry(root, width=5, justify='center')
FPSEntry.insert(0, '30')
FPSEntry.grid(row=5, column=4, sticky=Tk.W+Tk.E, ipadx=0, padx=0)
var = Tk.StringVar()
def RadioSelect():
    global fShowNote
    if(var.get() == 'Fret'):
        fShowNote = 1
    if(var.get() == 'Note'):
        fShowNote = 0
ShowLabel = Tk.Label(root, text='Showing', justify='right')
ShowLabel.grid(row=5, column=5)
RadioFret = Tk.Radiobutton(root, text='Fret', variable=var, value='Fret', command=RadioSelect)
RadioFret.grid(row=5, column=6, sticky=Tk.W+Tk.E, ipadx=0, padx=0)
RadioNote = Tk.Radiobutton(root, text='Note', variable=var, value='Note', command=RadioSelect)
RadioNote.grid(row=5, column=7, sticky=Tk.W+Tk.E, ipadx=0, padx=0)
var.set('Fret')

CommandStr=''
def GenerateMP4():
    global fFileLoaded, InputFileName
    global CommandStr
    if(fFileLoaded==0):
        return
    global notes, maxNotes
    idxFrame = 0
    fps = float(FPSEntry.get())
    maxSeconds = float(MaxTEntry.get())
    maxFrame = int(fps * maxSeconds)
    pathParent = Path(InputFileName).parent.absolute()
    MP4FileName = InputFileName.replace(".musicxml", ".mp4")
    idxCurrentNote = 0
    InitializeFretboard()
    for fr in range(maxFrame):
        sec = float(fr/fps)
        #notes List format [ 0:Measures from, 1:note length, 2:sec from, 3:sec end, 4:semitone list]
        if(sec>=float(notes[idxCurrentNote][2])):
            InitializeFretboard()
            semitones = notes[idxCurrentNote][4]
            if(semitones[0] != ''):
                DrawFretboard(idxCurrentNote)
            idxCurrentNote += 1
            if(idxCurrentNote >= maxNotes):
                idxCurrentNote = maxNotes-1
        OutFileName= '%s\\temp\\NoteImage%05d.png' % (pathParent, idxFrame)
        MainImg.save(OutFileName)
        ProgressLabel.configure(text='Progress: %d [s]' % int(idxFrame/fps))
        ProgressLabel.update()
        idxFrame += 1
    ProgressLabel.configure(text='Converting')
    ProgressLabel.update()
    CommandStr = 'ffmpeg.exe -y -r 30 -i %s' % pathParent + '\\temp\\NoteImage%05d.png -c:v libx265 -r 30 -pix_fmt yuv420p ' + MP4FileName
    subprocess.call(CommandStr, shell=True)
    CommandStr='del %s\\temp\\*.png' % pathParent
    subprocess.call(CommandStr, shell=True)
    ProgressLabel.configure(text='Finished')
    ProgressLabel.update()
ProgressLabel=Tk.Label(root, text='', width= 30)
ProgressLabel.grid(row=6, column=0, columnspan=4)
ConvertButton = Tk.Button(root, text='Generate MP4 (without audio) File', height=2, command=GenerateMP4)
ConvertButton.grid(row=6, column=6, columnspan=4, sticky=Tk.W+Tk.E)

# Tone Frame
ToneFrame = Tk.LabelFrame(root)
ToneFrame.grid(row=11, column=0, columnspan=10, sticky='ew')
ToneLabel = Tk.Label(ToneFrame, text='Recorded Tone Wave Files ')
ToneLabel.grid(row=1, column=0, columnspan=13, sticky=Tk.W+Tk.E, ipadx=0)
ToneFileNames=['','', '']
ToneWave = np.zeros((3,int(samplerate*5)), dtype=np.int16)
ToneC3Wave = []
ToneC4Wave = []
ToneC5Wave = []
def LoadTone(idx):
    global ToneFileNames, fSource
    filetypes = (("Tone", "*.wav"),('All files', '*.*'))
    FileName = filedialog.askopenfilename(initialdir='./', filetypes=filetypes)
    if(FileName != None):
        ToneFileNames[idx] = FileName
        varSource.set('Wave')
        fSource=1
def LoadToneC3():
    LoadTone(0)
    global ToneFileNames, samplerate, ToneC3Wave
    if(ToneFileNames[0]==None):
        return
    samplerate, ToneC3Wave = wavefile.read(ToneFileNames[0])
    ToneC3Entry.delete(0,'end')
    ToneC3Entry.insert(0, ToneFileNames[0])
def ClearToneC3():
    global ToneFileNames
    ToneFileNames[0]=''
    ToneC3Entry.delete(0,'end')
    ToneC3Entry.insert(0, 'No Tone Wave file is Loaded')
ToneC3Button = Tk.Button(ToneFrame, text='Load C3 Wav', width=15, command=LoadToneC3)
ToneC3Button.grid(row=2, column=0, columnspan=2, sticky=Tk.W+Tk.E)
ToneC3Entry = Tk.Entry(ToneFrame, width=80, justify='left')
ToneC3Entry.insert(0, 'No Tone Wave file is Loaded')
ToneC3Entry.grid(row=2, column=2, columnspan=10, sticky=Tk.W+Tk.E, ipadx=0, padx=0)
ClearC3Button = Tk.Button(ToneFrame, text='Clear', width=5, command=ClearToneC3)
ClearC3Button.grid(row=2, column=13, sticky=Tk.W+Tk.E)
def LoadToneC4():
    LoadTone(1)
    global ToneFileNames, samplerate, ToneC4Wave
    if(ToneFileNames[1]==None):
        return
    samplerate, ToneC4Wave = wavefile.read(ToneFileNames[1])
    ToneC4Entry.delete(0,'end')
    ToneC4Entry.insert(0, ToneFileNames[1])
def ClearToneC4():
    global ToneFileNames
    ToneFileNames[1]=''
    ToneC4Entry.delete(0,'end')
    ToneC4Entry.insert(0, 'No Tone Wave file is Loaded')
ToneC4Button = Tk.Button(ToneFrame, text='Load C4 Wav', width=15, command=LoadToneC4)
ToneC4Button.grid(row=3, column=0, columnspan=2, sticky=Tk.W+Tk.E)
ToneC4Entry = Tk.Entry(ToneFrame, width=80, justify='left')
ToneC4Entry.insert(0, 'No Tone Wave file is Loaded')
ToneC4Entry.grid(row=3, column=2, columnspan=10, sticky=Tk.W+Tk.E, ipadx=0, padx=0)
ClearC4Button = Tk.Button(ToneFrame, text='Clear', width=5, command=ClearToneC4)
ClearC4Button.grid(row=3, column=13, sticky=Tk.W+Tk.E)
def LoadToneC5():
    LoadTone(2)
    global ToneFileNames, samplerate, ToneC5Wave
    if(ToneFileNames[2]==None):
        return
    samplerate, ToneC5Wave = wavefile.read(ToneFileNames[2])
    ToneC5Entry.delete(0,'end')
    ToneC5Entry.insert(0, ToneFileNames[2])
def ClearToneC5():
    global ToneFileNames
    ToneFileNames[2]=''
    ToneC5Entry.delete(0,'end')
    ToneC5Entry.insert(0, 'No Tone Wave file is Loaded')
ToneC5Button = Tk.Button(ToneFrame, text='Load C5 Wav', width=15, command=LoadToneC5)
ToneC5Button.grid(row=4, column=0, columnspan=2, sticky=Tk.W+Tk.E)
ToneC5Entry = Tk.Entry(ToneFrame, width=80, justify='left')
ToneC5Entry.insert(0, 'No Tone Wave file is Loaded')
ToneC5Entry.grid(row=4, column=2, columnspan=10, sticky=Tk.W+Tk.E, ipadx=0, padx=0)
ClearC5Button = Tk.Button(ToneFrame, text='Clear', width=5, command=ClearToneC5)
ClearC5Button.grid(row=4, column=13, sticky=Tk.W+Tk.E)

def DrawFretboard(idxNote):
    global ttfontname, notes, font, backgroundRGB, textRGB, OpenStrings, fShowNote, MainImg
    semitones = notes[idxNote][4]
    if(semitones[0] == ''):
        return
    fontsize = int(TextSizeEntry.get())
    font = ImageFont.truetype(ttfontname, fontsize)
    Width = int(WidthEntry.get())
    Height = int(HeightEntry.get())
    #notes List format [ 0:Measures from, 1:note length, 2:sec from, 3:sec end, 4:semitone list]
    for i in range(len(semitones)):
        if(fShowNote == 0):
            # octave = int(int(semitones[i])/12)
            step = int(int(semitones[i]+8)%12)
            NoteString=''
            if(step == 0):
                NoteString = 'C'
            elif(step == 1):
                NoteString = 'C♯'
            elif(step == 2):
                NoteString = 'D'
            elif(step == 3):
                NoteString = 'D♯'
            elif(step == 4):
                NoteString = 'E'
            elif(step == 5):
                NoteString = 'F'
            elif(step == 6):
                NoteString = 'F♯'
            elif(step == 7):
                NoteString = 'G'
            elif(step == 8):
                NoteString = 'G♯'
            elif(step == 9):
                NoteString = 'A'
            elif(step == 10):
                NoteString = 'A♯'
            else:
                NoteString = 'B'
            TextImageW = int(TextWidthEntry.get())
            TextImageH = int(TextHeightEntry.get())
            TextCanvasSize= (TextImageW, TextImageH)
            TextImg = Image.new('RGBA', TextCanvasSize, (255,255,255,0))
            TextDraw = ImageDraw.Draw(TextImg)
            maskBackground = (255,255,255,0)
            MaskImg = Image.new('RGBA', TextCanvasSize, maskBackground)
            MaskDraw = ImageDraw.Draw(MaskImg)
            maskRGB= (0, 0, 0, 255)
            TextDraw.rectangle((0,0, TextImageW, TextImageH), fill=(255,255,255,0))
            TextDraw.text((0, 0), NoteString, fill=tuple(textRGB), font=font)
            MaskDraw.rectangle((0,0, TextImageW, TextImageH), fill=maskBackground)
            MaskDraw.text((0, 0), NoteString, fill=maskRGB, font=font)
        MainDraw = ImageDraw.Draw(MainImg)
        StringHeight= int(Height/6.5)
        FretWidth = int(Width/23)
        for nString in range(6):
            fret = int(semitones[i]) - int(OpenStrings[nString])
            if( (fret >= 0) & (fret < 23) ):
                X = fret * int(FretWidth)+int(FretWidth*0.1)
                Y = StringHeight*nString
                if(fShowNote == 1):
                    MainDraw.text((X,Y), str(fret), fill=tuple(textRGB), font=font)
                else:
                    MainImg.paste(TextImg, (X, Y, X+TextImageW, Y+TextImageH), MaskImg)
def ShowFrame(idxNote):
    global fFileLoaded
    if(fFileLoaded==0):
        return
    DrawFretboard(idxNote)
    Disp_img = MainImg.resize((int(Width/2),int(Height/2)))
    imgtk = ImageTk.PhotoImage(image=Disp_img)
    ImageLabel.imgtk = imgtk
    ImageLabel.configure(image=imgtk)
def ClearFretboard():
    global fFileLoaded, MainImg, MainDraw
    if(fFileLoaded==0):
        return
    global Height, Width, ttfontname, FretImg
    MainDraw = ImageDraw.Draw(MainImg)
    MainDraw.rectangle((0,0, Width, Height), fill=tuple(backgroundRGB))
    
def InitializeFretboard():
    global fFileLoaded, MainImg, MainDraw, fFretboardInitialized, FretImg
    if(fFileLoaded==0):
        return
    if(fFretboardInitialized == 1):
        MainImg = FretImg.copy()
        return
    global Height, Width, ttfontname
    ClearFretboard()
    StringHeight= int(Height/6.5)
    FretWidth = int(Width/23)
    MarkRadius = int(StringHeight*0.2)
    StringRGB = [64,64,64, 255]
    smallfont = ImageFont.truetype(ttfontname, 18)
    #Draw Fretboard
    for string in range(6):
        MainDraw.rectangle((0, int(StringHeight*(float(string)+0.5)), Width, int(StringHeight*(float(string)+0.5)+1)), fill=tuple(StringRGB))
    for fret in range(23):
        X = int(fret * FretWidth)
        XC = int(fret * FretWidth + FretWidth * 0.5)
        if(fret == 0):
            MainDraw.rectangle((X + FretWidth, 0, X + FretWidth +4, StringHeight*6), fill=tuple(StringRGB))
            MainDraw.text((int(FretWidth/10), int(StringHeight*6)), 'Open', fill=tuple(textRGB), font=smallfont)
        else:
            MainDraw.rectangle((X + FretWidth, 0, X + FretWidth +1, StringHeight*6), fill=tuple(StringRGB))
            MainDraw.text((int(fret*FretWidth + FretWidth/3), int(StringHeight*6)), str(fret), fill=tuple(textRGB), font=smallfont)
        if((fret == 3) | (fret == 5) | (fret == 7) | (fret == 9) | (fret == 15) | (fret == 17) | (fret == 19) | (fret == 21)):
            MainDraw.ellipse((XC-MarkRadius, int(StringHeight*3)-MarkRadius, XC+MarkRadius, int(StringHeight*3)+MarkRadius), fill=tuple(StringRGB))
        if(fret == 12):
            MainDraw.ellipse((XC-MarkRadius, int(StringHeight*1.8)-MarkRadius, XC+MarkRadius, int(StringHeight*1.8)+MarkRadius), fill=tuple(StringRGB))
            MainDraw.ellipse((XC-MarkRadius, int(StringHeight*4.2)-MarkRadius, XC+MarkRadius, int(StringHeight*4.2)+MarkRadius), fill=tuple(StringRGB))
    Disp_img = MainImg.resize((int(Width/2),int(Height/2)))
    FretImg = MainImg.copy()
    fFretboardInitialized = 1
    imgtk = ImageTk.PhotoImage(image=Disp_img)
    ImageLabel.imgtk = imgtk
    ImageLabel.configure(image=imgtk)

# Seek Frame
SeekFrame = Tk.LabelFrame(root)
SeekFrame.grid(row=12, column=0, columnspan=10, sticky='ew')
SourceLabel = Tk.Label(SeekFrame, text='Sound Source ')
SourceLabel.grid(row=1, column=0, columnspan=2, sticky=Tk.W+Tk.E, ipadx=0)
varSource = Tk.StringVar()
def SourceSelect():
    global fSource, ToneFileNames, varSource
    if(varSource.get() == 'Synth'):
        fSource = 0
    if(varSource.get() == 'Wave'):
        fSource = 0
        varSource.set('Synth')
        for i in range(3):
            if(ToneFileNames[i] !=''):
                fSource = 1
                varSource.set('Wave')
RadioSong = Tk.Radiobutton(SeekFrame, text='Synth.', variable=varSource, value='Synth', command=SourceSelect)
RadioSong.grid(row=1, column=2, sticky=Tk.W+Tk.E, ipadx=0, padx=0)
RadioTone = Tk.Radiobutton(SeekFrame, text='Wave', variable=varSource, value='Wave', command=SourceSelect)
RadioTone.grid(row=1, column=3, sticky=Tk.W+Tk.E, ipadx=0, padx=0)
varSource.set('Synth')
def Hz(note):
    return math.pow(2, (note-49)/12) * 440
def NoteWave(WaveOrg, SemitoneOrg, samplerate, SemitoneOut, LengthOut):
    # global WaveData
    fOrg = Hz(int(SemitoneOrg))
    fOut = Hz(int(SemitoneOut))
    LengthOrg = float(LengthOut)*int(samplerate)*float(fOut) / float(fOrg)
    if( int(LengthOrg) > len(WaveOrg)):
        WaveLong = np.zeros(int(LengthOrg), dtype=np.int16)
        WaveLong[0:len(WaveOrg)] += WaveOrg
        WaveData = signal.resample(WaveLong[0:int(LengthOrg)], int(float(LengthOut)*float(samplerate)))
    else:
        WaveData = signal.resample(WaveOrg[0:int(LengthOrg)], int(float(LengthOut)*float(samplerate)))
    return WaveData
def getToneWave(semitone, length):
    global ToneC3Wave, ToneC4Wave, ToneC5Wave, ToneFileNames, OpenStrings, samplerate
    if((semitone >= 20) & (semitone < 32)):
        if(ToneFileNames[0] != ''):
            WaveData = NoteWave(ToneC3Wave, 28, samplerate, semitone, length)
        elif(ToneFileNames[1] != ''):
            WaveData = NoteWave(ToneC4Wave, 40, samplerate, semitone, length)
        elif(ToneFileNames[2] != ''):
            WaveData = NoteWave(ToneC5Wave, 52, samplerate, semitone, length)
    if((semitone >= 32) & (semitone < 44)):
        if(ToneFileNames[1] != ''):
            WaveData = NoteWave(ToneC4Wave, 40, samplerate, semitone, length)
        elif(ToneFileNames[2] != ''):
            WaveData = NoteWave(ToneC5Wave, 52, samplerate, semitone, length)
        elif(ToneFileNames[0] != ''):
            WaveData = NoteWave(ToneC3Wave, 28, samplerate, semitone, length)
    if((semitone >= 44) & (semitone <= 66)):
        if(ToneFileNames[2] != ''):
            WaveData = NoteWave(ToneC5Wave, 52, samplerate, semitone, length)
        elif(ToneFileNames[1] != ''):
            WaveData = NoteWave(ToneC4Wave, 40, samplerate, semitone, length)
        elif(ToneFileNames[0] != ''):
            WaveData = NoteWave(ToneC3Wave, 28, samplerate, semitone, length)
    return WaveData
def ShowSingleChart(ScaleValue):
    global fFileLoaded, notes, maxNotes, maxMeasures, stepScale, MainImg, FretImg
    global fSource, ToneC3Wave, ToneC4Wave, ToneC5Wave, ToneFileNames, OpenStrings, samplerate, WaveData, fPlayNotes, Volume
    if(fFileLoaded==0):
        return
    if(fPlayNotes ==1):
        return
    idx = int(ScaleValue)
    if(idx >= maxNotes):
        return
    InitializeFretboard()
    #notes List format [ 0:Measures from, 1:note length, 2:sec from, 3:sec end, 4:semitone list]
    semitones = notes[idx][4]
    if(semitones[0] != ''):
        DrawFretboard(idx)
        length = float(notes[idx][1]) * 60.0 / TempoSong * 4.0

        if(fSource == 0):
            WaveData = NoteWave(SynthA5Wave, 61, samplerate, int(semitones[0]), length)
        else:
            WaveData = getToneWave(int(semitones[0]), length)
        for i in range(1, len(semitones)):
            if(fSource == 0):
                WaveData += NoteWave(SynthA5Wave, 61, samplerate, int(semitones[i]), length)
            else:
                WaveData += getToneWave(int(semitones[i]), length)

        # if(fSource == 0):
        #     # PlaySoundArray = FullTrack[int(float(notes[idx][2])*float(samplerate)):int(float(notes[idx][3])*float(samplerate))]
        #     # PlaySound = pygame.sndarray.make_sound(PlaySoundArray)
        #     # PlaySound.play()
        #     # PlaySound.set_volume(0.3)
        #     WaveData = NoteWave(SynthA5Wave , 61, samplerate, semitones[0], length)
        # elif(fSource == 1):
        #     #notes List format [ 0:Measures from, 1:note length, 2:sec from, 3:sec end, 4:semitone list]
        #     WaveData = getToneWave(int(semitones[0]), length)
        #     for i in range(1, len(semitones)):
        #         if(fSource == 0):
        #             WaveData += NoteWave(SynthA5Wave, 61, samplerate, int(semitones[i]), length)
        #         elif(fSource == 1):
        #             WaveData += getToneWave(int(semitones[i]), length)
        WaveOut = np.repeat(np.int16(WaveData).reshape(len(WaveData),1), 2, axis=1)
        pygame.mixer.init(frequency=samplerate, size=-16, channels=1)
        sound = pygame.sndarray.make_sound(WaveOut)
        sound.play()
        sound.set_volume(float(Volume))
    MeasureLabel.configure(text='Measure: %7.4f' % float(notes[idx][0]))
    Disp_img = MainImg.resize((int(Width/2),int(Height/2)))
    imgtk = ImageTk.PhotoImage(image=Disp_img)
    ImageLabel.imgtk = imgtk
    ImageLabel.configure(image=imgtk)
MeasureLabel = Tk.Label(SeekFrame, text='Measure: 0.0000', width=15)
MeasureLabel.grid(row=2, column=2, columnspan=5, sticky=Tk.W+Tk.E, ipadx=0)
PosLabel = Tk.Label(SeekFrame, text='Note Seek')
PosLabel.grid(row=3, column=0, sticky=Tk.E, ipadx=0)
def PrevNote():
    global fFileLoaded, notes
    if(fFileLoaded==0):
        return
    idxScale = FrameScale.get()
    if(idxScale < 1):
        return
    idxScale -= 1
    if(idxScale <0):
        idxScale = 0
    FrameScale.set(idxScale)
PrevButton = Tk.Button(SeekFrame, text='|<', width=2, command=PrevNote)
PrevButton.grid(row=3, column=1, sticky=Tk.E)
FrameScale = Tk.Scale(SeekFrame, orient='horizontal', command=ShowSingleChart, cursor='arrow', \
                      from_=0, to=maxNotes , resolution=1)
FrameScale.set(0)
FrameScale.configure(showvalue=0)
FrameScale.grid(row=3,column=2, columnspan=5,sticky='ew')
def NextNote():
    global fFileLoaded, maxNotes
    if(fFileLoaded==0):
        return
    idxScale = FrameScale.get()
    if(idxScale >= maxNotes):
        FrameScale.set(maxNotes)
        return
    idxScale +=1
    FrameScale.set(idxScale)
NextButton = Tk.Button(SeekFrame, text='>|', width=2, command=NextNote)
NextButton.grid(row=3, column=7, sticky=Tk.W)
def SetVolume(value):
    global Volume
    Volume = float(value)
VolLabel = Tk.Label(SeekFrame, text='   Volume')
VolLabel.grid(row=1, column=10, sticky=Tk.W+Tk.E, ipadx=0)
VolScale = Tk.Scale(SeekFrame, orient='vertical', command=SetVolume, cursor='arrow', \
                      from_=1.0, to=0 , resolution=0.1, length=50)
VolScale.set(0.3)
VolScale.grid(row=2, rowspan=2, column=10, sticky='ew')

varTick = Tk.IntVar()
TickBox = Tk.Checkbutton(SeekFrame, text='Metronome', variable=varTick, onvalue=1, offvalue=0)
TickBox.grid(row=1, column=13, sticky=Tk.W+Tk.E, ipadx=0)
def PlaySection():
    global fPlayNotes, idxPlayNotes, idxSectionFrom, idxNotePlayed
    if(fPlayNotes == 0):
        idxPlayNotes = idxSectionFrom
        idxNotePlayed = idxSectionFrom
        SectionPlayButton.configure(text='Playing')
        # Clearing Queue
        while(queue.empty() != True):
            try:
                q=queue.get()
            except Empty:
                continue
        fPlayNotes = 1
    else:
        SectionPlayButton.configure(text='Play Section')
        idxPlayNotes = idxSectionFrom
        idxNotePlayed = idxSectionFrom
        fPlayNotes = 0
SectionPlayButton = Tk.Button(SeekFrame, text='Play Section', width=12, command=PlaySection)
SectionPlayButton.grid(row=1, column=14, columnspan=2, sticky=Tk.W+Tk.E, ipadx=0)
def TempoDown10():
    global TempoPlayNotes, fPlaymaxNotes
    TempoPlayNotes -= 10
    if(TempoPlayNotes<1):
        TempoPlayNotes = 1
    TempoLabel.configure(text='Tempo: %d' % TempoPlayNotes)
TempoDown10Button = Tk.Button(SeekFrame, text='<-10', width=5, command=TempoDown10)       
TempoDown10Button.grid(row=2, column=11, sticky=Tk.E)
def TempoDown():
    global TempoPlayNotes, fPlaymaxNotes
    TempoPlayNotes -= 1
    if(TempoPlayNotes<1):
        TempoPlayNotes = 1
    TempoLabel.configure(text='Tempo: %d' % TempoPlayNotes)
TempoDownButton = Tk.Button(SeekFrame, text='<-1', width=5, command=TempoDown)       
TempoDownButton.grid(row=2, column=12, sticky=Tk.E)
TempoLabel = Tk.Label(SeekFrame, text='Tempo: 120')
TempoLabel.grid(row=2, column=13, sticky=Tk.W+Tk.E, ipadx=0)
def TempoUp():
    global TempoPlayNotes, fPlaymaxNotes
    TempoPlayNotes += 1
    TempoLabel.configure(text='Tempo: %d' % TempoPlayNotes)
TempoUpButton = Tk.Button(SeekFrame, text='+1>', width=5, command=TempoUp)       
TempoUpButton.grid(row=2, column=14, sticky=Tk.W)
def TempoUp10():
    global TempoPlayNotes, fPlaymaxNotes
    TempoPlayNotes += 10
    TempoLabel.configure(text='Tempo: %d' % TempoPlayNotes)
TempoUp10Button = Tk.Button(SeekFrame, text='+10>', width=5, command=TempoUp10)       
TempoUp10Button.grid(row=2, column=15, sticky=Tk.W)
def SetSectionFrom():
    global fPlayNotes, maxNotes, idxSectionFrom, idxSectionTo, notes
    if(fPlayNotes == 0):
        idxSectionFrom = FrameScale.get()
        SectionFromLabel.configure(text='%d' % int(float(notes[idxSectionFrom][0])))
        if(idxSectionTo<=idxSectionFrom):
            idxSectionTo = idxSectionFrom + 1
            if(idxSectionTo>maxNotes):
                idxSectionTo = maxNotes
SectionFromSetButton = Tk.Button(SeekFrame, text='Set Sction From', width=12, command=SetSectionFrom)
SectionFromSetButton.grid(row=3, column=11, sticky=Tk.E, ipadx=0)
SectionFromLabel = Tk.Label(SeekFrame, text='0', width=5)
SectionFromLabel.grid(row=3, column=12, sticky=Tk.W+Tk.E, ipadx=0)
varLoop=Tk.IntVar()
LoopBox = Tk.Checkbutton(SeekFrame, text='LOOP', variable=varLoop, onvalue=1, offvalue=0)
LoopBox.grid(row=3, column=13, sticky=Tk.W+Tk.E, ipadx=0)
SectionToLabel = Tk.Label(SeekFrame, text='1', width=5)
SectionToLabel.grid(row=3, column=14, sticky=Tk.W+Tk.E, ipadx=0)
def SetSectionTo():
    global fPlayNotes, maxNotes, idxSectionFrom, idxSectionTo
    if(fPlayNotes == 0):
        idxSectionTo = FrameScale.get()
        SectionToLabel.configure(text='%d' % int(float(notes[idxSectionTo][0])))
        if(idxSectionFrom>=idxSectionTo):
            idxSectionFrom = idxSectionTo - 1
            if(idxSectionFrom<0):
                idxSectionFrom = 0
SectionToSetButton = Tk.Button(SeekFrame, text='Set Section To', width=12, command=SetSectionTo)
SectionToSetButton.grid(row=3, column=15, sticky=Tk.W, ipadx=0)

#Note Play Thread
def RenderPlayNote(queue):
    global fFileLoaded, fSource, fPlayNotes, notes, idxPlayNotes, TempoSong, TempoPlayNotes, maxNotes, idxSectionTo
    global Tick0Wave, Tick1Wave, varTick
    global fWindowClose
    while (fWindowClose == 0):
        if(fFileLoaded == 0):
            time.sleep(1)
            continue
        if(fPlayNotes == 0):
            time.sleep(1)
            continue
        if(queue.qsize()>4):
            time.sleep(0.5)
            continue
        if(idxPlayNotes <= idxSectionTo):
            idxQueue = idxPlayNotes
            TempoCurrent = TempoPlayNotes
            #notes List format [ 0:Measures from, 1:note length, 2:sec from, 3:sec end, 4:semitone list]
            semitones = notes[idxPlayNotes][4]
            if(semitones[0] != ''):
                length = float(notes[idxPlayNotes][1]) * 60.0 / TempoSong * 4.0
                # length = float(notes[idxPlayNotes][3]) - float(notes[idxPlayNotes][2])
                PlayLength = float(length) * float(TempoSong) / float(TempoCurrent)
                if(fSource == 0):
                    WaveData = NoteWave(SynthA5Wave, 61, samplerate, int(semitones[0]), PlayLength)
                else:
                    WaveData = getToneWave(int(semitones[0]), PlayLength)
                for i in range(1, len(semitones)):
                    if(fSource == 0):
                        WaveData += NoteWave(SynthA5Wave, 61, samplerate, int(semitones[i]), PlayLength)
                    else:
                        WaveData += getToneWave(int(semitones[i]), PlayLength)
                
                if(varTick.get() == 1 ):
                    BaseBeat = (float(notes[idxPlayNotes][0]) % 1.0) * 4.0
                    NoteEndBeat = BaseBeat + float(notes[idxPlayNotes][1])*4.0
                    if(BaseBeat == 0):
                        TickPosition = WaveData[0:len(Tick0Wave)]
                        TickPosition += Tick0Wave
                        WaveData[0:len(Tick0Wave)] = TickPosition
                    elif(BaseBeat % 1.0 == 0):
                        TickPosition = WaveData[0:len(Tick1Wave)]
                        TickPosition += Tick1Wave
                        WaveData[0:len(Tick1Wave)] = TickPosition
                    idxBeat = int(BaseBeat) +1.0
                    while(idxBeat < NoteEndBeat):
                        LeadingBeat = float(idxBeat) - BaseBeat
                        StartPos = int(LeadingBeat * 60 / TempoCurrent * samplerate)
                        if(float(idxBeat)%4.0 == 0):
                            TickPosition = WaveData[StartPos : StartPos+len(Tick0Wave)]
                            if(len(TickPosition)>0):
                                TickPosition += Tick0Wave
                                WaveData[StartPos : StartPos+len(Tick0Wave)] = TickPosition
                        else:
                            TickPosition = WaveData[StartPos : StartPos+len(Tick1Wave)]
                            if(len(TickPosition)>0):
                                TickPosition += Tick1Wave
                                WaveData[StartPos : StartPos+len(Tick1Wave)] = TickPosition
                        idxBeat += 1.0
                queue.put((idxQueue, WaveData))
            else:
                length = float(notes[idxPlayNotes][1]) * 60.0 / TempoSong * 4.0
                PlayLength = float(length) * float(TempoSong) / float(TempoPlayNotes)
                WaveData = np.zeros(int(float(PlayLength*float(samplerate))), dtype=np.int16)
                if(varTick.get() == 1 ):
                    Beat = (float(notes[idxPlayNotes][0]) % 1.0) * 4.0
                    if(Beat == 0):
                        TickPosition = WaveData[0:len(Tick0Wave)]
                        TickPosition += Tick0Wave
                        WaveData[0:len(Tick0Wave)] = TickPosition
                    elif(Beat % 1.0 == 0):
                        TickPosition = WaveData[0:len(Tick1Wave)]
                        TickPosition += Tick1Wave
                        WaveData[0:len(Tick1Wave)] = TickPosition
                queue.put((idxQueue, WaveData))
            idxPlayNotes += 1
        if(idxPlayNotes >= maxNotes-1):
            idxPlayNotes = maxNotes-1

def SendPlayNote(queue):
    global fFileLoaded, fSource, fPlayNotes, idxPlayNotes, idxSectionFrom, idxSectionTo, MainImg, FretImg, Width, Height, Volume
    global fWindowClose
    while (fWindowClose == 0):
        if(fFileLoaded == 0):
            time.sleep(1)
            continue
        if(fPlayNotes == 0):
            time.sleep(1)
            continue
        try:
            ContentQueue = queue.get()
            idxNotePlayed = ContentQueue[0]
            WaveData = ContentQueue[1]
        except Empty:
            continue
        else:
            WaveOut = np.repeat(np.int16(WaveData).reshape(len(WaveData),1), 2, axis=1)
            pygame.mixer.init(frequency=samplerate, size=-16, channels=1)
            sound = pygame.sndarray.make_sound(WaveOut)
            while(pygame.mixer.get_busy() ):
                if(fPlayNotes==0):
                    sound.stop()
                    break
                continue
            if(fPlayNotes==1):
                sound.play()
                sound.set_volume(float(Volume))
                InitializeFretboard()
                ShowFrame(idxNotePlayed)
                # FrameScale.set(int(idxNotePlayed))
                # queue2.put(idxNotePlayed)
            queue.task_done()
            FrameScale.set(idxNotePlayed)
            MeasureLabel.configure(text='Measure: %7.4f' % float(notes[idxNotePlayed][0]))
            FrameScale.update()
            if(idxNotePlayed >= idxSectionTo):
                if(varLoop.get() == 0):
                    if(fPlayNotes==1):
                        PlaySection()
                else:
                    idxPlayNotes = idxSectionFrom
            if(idxNotePlayed >= maxNotes-1):
                if(fPlayNotes==1):
                    PlaySection()

queue = Queue()
RenderAudioThread = Thread(target=RenderPlayNote, args=(queue,), daemon=True)
RenderAudioThread.start()
PlayThread = Thread(target=SendPlayNote, args=(queue,), daemon=True)
PlayThread.start()

def WindowClosing():
    global fPlayNotes, fWindowClose
    fPlayNotes=0
    fWindowClose = 1
    time.sleep(0.2)
    print('Windows is closing')
    RenderAudioThread.join()
    print('Render Thread stopped')
    PlayThread.join()
    print('Play Thread stopped')
    # ShowThread.join()
    # while(queue.empty() != True):
    #     try:
    #         q=queue.get()
    #     except Empty:
    #         continue
    #     queue.task_done()
    # queue.join()
    # print('Queue Thread stopped')
    root.destroy()
    print('Window Destoryed')

root.protocol("WM_DELETE_WINDOW", WindowClosing)
root.mainloop()

