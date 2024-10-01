# -*- coding: utf-8 -*-
"""
Created on Fri Dec 30 20:37:18 2022

@author: ktake

https://gis.stackexchange.com/questions/58271/using-python-to-parse-an-xml-containing-gml-tags

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

root = Tk.Tk()
root.title('Music XML Conversion Tool: Fretboard Chart to mp4')

InputFileName=''
fFileLoaded = 0
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
FileEntry.grid(row=0, column=2, columnspan=10, sticky=Tk.W+Tk.E, ipadx=0, padx=0)

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
    return value

# semitones of openstrings
# E4=12*4+4, B3=12*3+11, G3=12*3+7, D3=12*3+2, A2=12*2+9, E2=12*2+4
OpenStrings=[52, 47, 43, 38, 33, 28]

notes = []
maxNotes = 0
maxMeasures = 0
fFileLoaded = 0
def LoadNotes():
    global InputFileName, fFileLoaded, Lyrics, Seconds, TonePitch, Beats, notes, maxNotes, maxMeasures
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
        sec0 = 0
        sec1 = 0
        idxMeasure = 0
        Measures = 0.0
        for measure in root.iter('measure'):
            fracMeasure = 0.0
            for note in measure.iter(tag='note'):
                NoteString=''
                if(note.find('pitch') != None):
                    step = note.find('pitch/step')
                    octave = note.find('pitch/octave')
                    alter=note.find("pitch/alter")
                    alterValue=0
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
                    length = note.find("type")
                    chord = note.find("chord")
                    if(chord == None):
                        fracMeasure += float(getLengthOfNote(length.text))
                    Measures = float(idxMeasure)+fracMeasure
                    sec0 = float(Measures- float(getLengthOfNote(length.text))) * 60.0/tempoValue*4.0
                    sec1 = float(Measures) * 60.0/tempoValue*4.0
                    notes.append((sec0, sec1, getSemitoneNumber(step.text, octave.text, alterValue), NoteString, float(Measures- float(getLengthOfNote(length.text)))))
                elif(note.find('rest') != None):
                    NoteString+='Rest'
                    length = note.find("type")
                    fracMeasure += float(getLengthOfNote(length.text))
                    Measures = float(idxMeasure) + fracMeasure
                    sec0 = float(Measures- float(getLengthOfNote(length.text))) * 60.0/tempoValue*4.0
                    sec1 = float(Measures) * 60.0/tempoValue*4.0
                    notes.append((sec0, sec1, '', NoteString, float(Measures- float(getLengthOfNote(length.text)))))
            idxMeasure +=1
        maxNotes=len(notes)
        maxMeasures = idxMeasure
        FrameScale.configure(to=maxMeasures*4)
        FrameScale.set(0)
        fFileLoaded = 1
    
FrameTitleLabel = Tk.Label(root, text='Fretboard Chart Frame Format', width=30)
FrameTitleLabel.grid(row=1, column=0, columnspan=8, sticky=Tk.W+Tk.E, ipadx=0)
SizeLabel = Tk.Label(root, text='Frame Width x Height', width=15)
SizeLabel.grid(row=2, column=0, columnspan=2, sticky=Tk.W+Tk.E, ipadx=0)
WidthEntry = Tk.Entry(root, width=10, justify='center')
WidthEntry.insert(0, '1280')
WidthEntry.grid(row=2, column=2, sticky=Tk.W+Tk.E, ipadx=0, padx=0)
CrossLabel = Tk.Label(root, text=' x ', width=5, justify='center')
CrossLabel.grid(row=2, column=3, sticky=Tk.W+Tk.E, ipadx=0)
HeightEntry = Tk.Entry(root, width=10, justify='center')
HeightEntry.insert(0, '360')
HeightEntry.grid(row=2, column=4, sticky=Tk.W+Tk.E, ipadx=0, padx=0)
BGLabel = Tk.Label(root, text='Background color', width=5, justify='center')
BGLabel.grid(row=2, column=5, columnspan=2, sticky=Tk.W+Tk.E, ipadx=0)
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
BGColorButton.grid(row=2, column=7, sticky=Tk.W+Tk.E)

LyricLabel = Tk.Label(root, text='Note Text size and Font size', width=15)
LyricLabel.grid(row=3, column=0, columnspan=2, sticky=Tk.W+Tk.E, ipadx=0)
TextWidthEntry = Tk.Entry(root, width=10, justify='center')
TextWidthEntry.insert(0, '120')
TextWidthEntry.grid(row=3, column=2, sticky=Tk.W+Tk.E, ipadx=0, padx=0)
TextCrossLabel = Tk.Label(root, text=' x ', width=5, justify='center')
TextCrossLabel.grid(row=3, column=3, sticky=Tk.W+Tk.E, ipadx=0)
TextHeightEntry = Tk.Entry(root, width=10, justify='center')
TextHeightEntry.insert(0, '40')
TextHeightEntry.grid(row=3, column=4, sticky=Tk.W+Tk.E, ipadx=0, padx=0)
TextSizeLabel = Tk.Label(root, text='Font size [pt]', width=10)
TextSizeLabel.grid(row=3, column=5, sticky=Tk.W+Tk.E, ipadx=0)
TextSizeEntry = Tk.Entry(root, width=5, justify='center')
TextSizeEntry.insert(0, '34')
TextSizeEntry.grid(row=3, column=6, sticky=Tk.W+Tk.E, ipadx=0, padx=0)
TextColorLabel = Tk.Label(root, text='Font Color', width=10)
TextColorLabel.grid(row=3, column=7, sticky=Tk.W+Tk.E, ipadx=0)
def FontColorChooser():
    global textRGB
    colors=askcolor('#%02x%02x%02x' % (textRGB[0],textRGB[1],textRGB[2]), title='Choose Font Color')
    textRGB[0] = colors[0][0]
    textRGB[1] = colors[0][1]
    textRGB[2] = colors[0][2]
    FontColorButton.configure(bg=colors[1])
FontColorButton=Tk.Button(root, text='Color', bg='#A0FFFF',  command=FontColorChooser)
FontColorButton.grid(row=3, column=8, sticky=Tk.W+Tk.E)


VideoLabel = Tk.Label(root, text='Video Max. Length t[sec]=', width=15)
VideoLabel.grid(row=4, column=0, columnspan=2, sticky=Tk.W+Tk.E, ipadx=0)
MaxTEntry = Tk.Entry(root, width=10, justify='center')
MaxTEntry.insert(0, '90')
MaxTEntry.grid(row=4, column=2, sticky=Tk.W+Tk.E, ipadx=0, padx=0)
FPSLabel = Tk.Label(root, text='FPS=', width=5, justify='right')
FPSLabel.grid(row=4, column=3, sticky=Tk.W+Tk.E, ipadx=0)
FPSEntry = Tk.Entry(root, width=10, justify='center')
FPSEntry.insert(0, '30')
FPSEntry.grid(row=4, column=4, sticky=Tk.W+Tk.E, ipadx=0, padx=0)

var = Tk.StringVar()
def RadioSelect():
    global fShowNote
    if(var.get() == 'Note'):
        fShowNote = 1
    if(var.get() == 'Fret'):
        fShowNote = 0
RadioNote = Tk.Radiobutton(root, text='Note', variable=var, value='Note', command=RadioSelect)
RadioNote.grid(row=4, column=5, sticky=Tk.W+Tk.E, ipadx=0, padx=0)
RadioFret = Tk.Radiobutton(root, text='Fret', variable=var, value='Fret', command=RadioSelect)
RadioFret.grid(row=4, column=6, sticky=Tk.W+Tk.E, ipadx=0, padx=0)
var.set('Note')


ttfontname = "c:\\Windows\\Fonts\\meiryob.ttc"
fontsize = 16
Width = 1280
Height = 360
TextImageW = 30
TextImageH = 20

MainCanvasSize = (Width, Height)
backgroundRGB = [140,100,64, 255]
textRGB = [128,255,255,255]
MainImg = Image.new('RGBA', MainCanvasSize, tuple(backgroundRGB))
MainDraw = ImageDraw.Draw(MainImg)
font = ImageFont.truetype(ttfontname, fontsize)
TextCanvasSize= (TextImageW, TextImageH)
TextImg = Image.new('RGBA', TextCanvasSize, (255,255,255,0))
TextDraw = ImageDraw.Draw(TextImg)

idxFrame = 0
fps = 30
maxSeconds = 90

# ImageLabel = Tk.Label(root, bg='white', fg='black', borderwidth=1, relief="solid")
ImageLabel = Tk.Label(root)
ImageLabel.grid(row=7, column=0, columnspan=10, sticky=Tk.NW+Tk.SE)
Disp_img = MainImg.resize((int(Width/2),int(Height/2)))
imgtk = ImageTk.PhotoImage(image=Disp_img)
ImageLabel.imgtk = imgtk
ImageLabel.configure(image=imgtk)

fShowNote = 1
def DrawFretboard(idxNote):
    global ttfontname, notes, font, backgroundRGB, textRGB, OpenStrings, fShowNote

    fontsize = int(TextSizeEntry.get())
    Width = int(WidthEntry.get())
    Height = int(HeightEntry.get())
    TextImageW = int(TextWidthEntry.get())
    TextImageH = int(TextHeightEntry.get())
    font = ImageFont.truetype(ttfontname, fontsize)
    
    TextCanvasSize= (TextImageW, TextImageH)
    TextImg = Image.new('RGBA', TextCanvasSize, (255,255,255,0))
    TextDraw = ImageDraw.Draw(TextImg)
    TextDraw.text((0, 0), notes[int(idxNote)][3], fill=tuple(textRGB), font=font)
    maskBackground = (255,255,255,0)
    MaskImg = Image.new('RGBA', TextCanvasSize, maskBackground)
    MaskDraw = ImageDraw.Draw(MaskImg)
    maskRGB= (0, 0, 0, 255)
    MaskDraw.text((0, 0), notes[int(idxNote)][3], fill=maskRGB, font=font)

    MainDraw = ImageDraw.Draw(MainImg)

    StringHeight= int(Height/6.5)
    FretWidth = int(Width/23)
    if(notes[int(idxNote)][2] !=''):
        for nString in range(6):
            fret = int(notes[int(idxNote)][2]) - int(OpenStrings[nString])
            if( (fret >= 0) & (fret < 23) ):
                X = fret * int(FretWidth)+int(FretWidth*0.1)
                Y = StringHeight*nString
                if(fShowNote == 1):
                    MainImg.paste(TextImg, (X, Y, X+TextImageW, Y+TextImageH), MaskImg)
                else:
                    MainDraw.text((X,Y), str(fret), fill=tuple(textRGB), font=font)

def ShowFrame(idxNote):
    global fFileLoaded
    if(fFileLoaded==0):
        return

    DrawFretboard(idxNote)
    
    Disp_img = MainImg.resize((int(Width/2),int(Height/2)))
    imgtk = ImageTk.PhotoImage(image=Disp_img)
    ImageLabel.imgtk = imgtk
    ImageLabel.configure(image=imgtk)

def InitializeFretboard():
    global fFileLoaded
    if(fFileLoaded==0):
        return
    global Height, Width, ttfontname
    MainDraw = ImageDraw.Draw(MainImg)
    MainDraw.rectangle((0,0, Width, Height), fill=tuple(backgroundRGB))
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
    imgtk = ImageTk.PhotoImage(image=Disp_img)
    ImageLabel.imgtk = imgtk
    ImageLabel.configure(image=imgtk)


SeekFrame = Tk.LabelFrame(root)
SeekFrame.grid(row=8, column=0, columnspan=10, sticky='ew')
BeatLabel = Tk.Label(SeekFrame, text='  Resolution  Beat ')
BeatLabel.grid(row=5, column=0, sticky=Tk.W+Tk.E, ipadx=0)
varBeat = Tk.StringVar()
stepScale = 4
stepScaleOld = 4
def BeatSelect():
    global Tempo, stepScale, stepScaleOld
    if(varBeat.get() == '1/4'):
        stepScale = 4
    if(varBeat.get() == '1/8'):
        stepScale = 8
    if(varBeat.get() == '1/16'):
        stepScale = 16
    if(varBeat.get() == '1/32'):
        stepScale = 32
    if(varBeat.get() == '1/64'):
        stepScale = 64
    FrameScale.set(int(FrameScale.get())*stepScale/stepScaleOld)
    FrameScale.configure(to=maxMeasures*stepScale)
    stepScaleOld = stepScale
RadioBeat4 = Tk.Radiobutton(SeekFrame, text='1/4', variable=varBeat, value='1/4', command=BeatSelect)
RadioBeat4.grid(row=5, column=6, sticky=Tk.W+Tk.E, ipadx=0, padx=0)
RadioBeat8 = Tk.Radiobutton(SeekFrame, text='1/8', variable=varBeat, value='1/8', command=BeatSelect)
RadioBeat8.grid(row=5, column=7, sticky=Tk.W+Tk.E, ipadx=0, padx=0)
RadioBeat16 = Tk.Radiobutton(SeekFrame, text='1/16', variable=varBeat, value='1/16', command=BeatSelect)
RadioBeat16.grid(row=5, column=8, sticky=Tk.W+Tk.E, ipadx=0, padx=0)
RadioBeat32 = Tk.Radiobutton(SeekFrame, text='1/32', variable=varBeat, value='1/32', command=BeatSelect)
RadioBeat32.grid(row=5, column=9, sticky=Tk.W+Tk.E, ipadx=0, padx=0)
RadioBeat64 = Tk.Radiobutton(SeekFrame, text='1/64', variable=varBeat, value='1/64', command=BeatSelect)
RadioBeat64.grid(row=5, column=10, sticky=Tk.W+Tk.E, ipadx=0, padx=0)
varBeat.set('1/4')

def ShowSingleChart(ScaleValue):
    global fFileLoaded, notes, maxNotes, maxMeasures, stepScale
    if(fFileLoaded==0):
        return
    CurrentMeasure=float(ScaleValue)/float(stepScale)
    InitializeFretboard()
    for idx in range(maxNotes):
        if(float(CurrentMeasure)  <= float(notes[idx][4])):
            if(notes[idx][2] !=''):
                DrawFretboard(idx)
            idxMore = 1
            if(idx < maxNotes-1):
                while(float(notes[idx][0]) == float(notes[idx+idxMore][0])):
                    if(notes[idx+idxMore][2] !=''):
                        DrawFretboard(idx+idxMore)
                    idxMore += 1
            break
    Disp_img = MainImg.resize((int(Width/2),int(Height/2)))
    imgtk = ImageTk.PhotoImage(image=Disp_img)
    ImageLabel.imgtk = imgtk
    ImageLabel.configure(image=imgtk)
    MeasureLabel.configure(text='Measure: %d' % int(CurrentMeasure))
PosLabel = Tk.Label(SeekFrame, text='Position')
PosLabel.grid(row=8, column=0, sticky=Tk.W+Tk.E, ipadx=0)
FrameScale = Tk.Scale(SeekFrame, orient='horizontal', command=ShowSingleChart, cursor='arrow', \
                      from_=0, to=maxMeasures , resolution=1)
FrameScale.set(0)
FrameScale.grid(row=8,column=1, columnspan=10,sticky='ew')
MeasureLabel = Tk.Label(SeekFrame, text='Measure: 0', width=15)
MeasureLabel.grid(row=8, column=11, columnspan=3, sticky=Tk.W+Tk.E, ipadx=0)


def GenerateMP4():
    global fFileLoaded
    if(fFileLoaded==0):
        return
    global notes, maxNotes
    InitializeFretboard()

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
        if(sec>=float(notes[idxCurrentNote][0])):
            InitializeFretboard()
            if(notes[idxCurrentNote][2] !=''):
                DrawFretboard(idxCurrentNote)
            idxCurrentNote += 1
            while(float(notes[idxCurrentNote-1][0]) == float(notes[idxCurrentNote][0])):
                if(notes[idxCurrentNote][2] !=''):
                    DrawFretboard(idxCurrentNote)
                idxCurrentNote += 1
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
ConvertButton = Tk.Button(root, text='Generate MP4 File', height=2, command=GenerateMP4)
ConvertButton.grid(row=10, column=0, columnspan=4, sticky=Tk.W+Tk.E)
ProgressLabel=Tk.Label(root, text='', width= 10)
ProgressLabel.grid(row=10, column=6, columnspan=3)

root.mainloop()
