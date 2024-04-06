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
import numpy as np
from PIL import Image, ImageTk
from PIL import ImageDraw
from PIL import ImageFont
from pathlib import Path

root = Tk.Tk()
root.title('Music XML Conversion Tool: Lyric to mp4')

InputFileName=''
fFileLoaded = 0
def LoadFile():
    global InputFileName, fFileLoaded
    filetypes = (("Music XML", "*.musicxml"),('All files', '*.*'))
    InputFileName = filedialog.askopenfilename(initialdir='./', filetypes=filetypes)
    LoadLyric()
    if(fFileLoaded==1):
        FileEntry.delete(0, Tk.END)
        FileEntry.insert(0, InputFileName)
        InitializeLyricsMotion()
LoadButton = Tk.Button(root, text='Clic to Read Music XML File', width=25, command=LoadFile)
LoadButton.grid(row=0, column=0, columnspan=2, sticky=Tk.W+Tk.E)

FileEntry = Tk.Entry(root, width=80, justify='left')
FileEntry.insert(0, 'No Music XML file is Loaded')
FileEntry.grid(row=0, column=2, columnspan=6, sticky=Tk.W+Tk.E, ipadx=0, padx=0)


Lyrics=[]
Seconds=[]
Keyboards=[]
Beats=[]
idxNote=0
def LoadLyric():
    global InputFileName, fFileLoaded, Lyrics, Seconds, Keyboards, Beats, idxNote, maxNotes
    if(InputFileName!=''):
        tree = ET.parse(InputFileName)
        root = tree.getroot()
        for tempo in root.iter(tag="sound"):
            if('tempo' in tempo.attrib):
                tempoText = "%s" % tempo.attrib
                tempoValue = float(re.findall('[0-9]+', tempoText.split()[1])[0])
        nMeasure = 0
        semitone = 0
        sec = 0
        for measure in root.iter('measure'):
            sec = float(nMeasure) * 60.0/tempoValue*4.0
            position = 0
            for note in measure.iter(tag='note'):
                text=note.find("lyric/text")
                if(text!=None):
                    Lyrics.append(text.text)
                    # duration=note.find("duration")
                    Beats.append(position)
                    noteType=note.find("type")
                    if(noteType.text == 'whole'):
                        position += 4
                    elif(noteType.text == 'half'):
                        position += 2
                    elif(noteType.text == 'quarter'):
                        position += 1
                    elif(noteType.text == 'eighth'):
                        position += 0.5
                    elif(noteType.text == '16th'):
                        position += 0.25
                    elif(noteType.text == '32nd'):
                        position += 0.125
                    elif(noteType.text == '64th'):
                        position += 0.0625
                    semitone = 0
                    step=note.find("pitch/step")
                    if(step.text == 'D'):
                        semitone = 2
                    elif(step.text == 'E'):
                        semitone = 4
                    elif(step.text == 'F'):
                        semitone = 5
                    elif(step.text == 'G'):
                        semitone = 7
                    elif(step.text == 'A'):
                        semitone = 9
                    elif(step.text == 'B'):
                        semitone = 11
                    alter=note.find("pitch/alter")
                    if(alter != None):
                        semitone += int(alter.text)
                    octave=note.find("pitch/octave")
                    Keyboards.append(int(octave.text)*11+semitone)
                    Seconds.append(sec+position*60.0/float(tempoValue))
                    idxNote += 1
                else:
                    noteType=note.find("type")
                    if(noteType.text == 'whole'):
                        position += 4
                    elif(noteType.text == 'half'):
                        position += 2
                    elif(noteType.text == 'quarter'):
                        position += 1
                    elif(noteType.text == 'eighth'):
                        position += 0.5
                    elif(noteType.text == '16th'):
                        position += 0.25
                    elif(noteType.text == '32nd'):
                        position += 0.125
                    elif(noteType.text == '64th'):
                        position += 0.0625
            nMeasure +=1
        maxNotes=idxNote
        fFileLoaded = 1
    
FrameTitleLabel = Tk.Label(root, text='Frame Formats and Lyric Movements', width=30)
FrameTitleLabel.grid(row=1, column=0, columnspan=8, sticky=Tk.W+Tk.E, ipadx=0)
SizeLabel = Tk.Label(root, text='Frame Width x Height', width=15)
SizeLabel.grid(row=2, column=0, columnspan=2, sticky=Tk.W+Tk.E, ipadx=0)
WidthEntry = Tk.Entry(root, width=10, justify='center')
WidthEntry.insert(0, '1280')
WidthEntry.grid(row=2, column=2, sticky=Tk.W+Tk.E, ipadx=0, padx=0)
CrossLabel = Tk.Label(root, text=' x ', width=5, justify='center')
CrossLabel.grid(row=2, column=3, sticky=Tk.W+Tk.E, ipadx=0)
HeightEntry = Tk.Entry(root, width=10, justify='center')
HeightEntry.insert(0, '720')
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
BGColorButton=Tk.Button(root, text='Color', bg='#00FF00',  command=BackgroundColorChooser)
BGColorButton.grid(row=2, column=7, sticky=Tk.W+Tk.E)

LyricLabel = Tk.Label(root, text='Lyric Text size and Font size', width=15)
LyricLabel.grid(row=3, column=0, columnspan=2, sticky=Tk.W+Tk.E, ipadx=0)
TextWidthEntry = Tk.Entry(root, width=10, justify='center')
TextWidthEntry.insert(0, '360')
TextWidthEntry.grid(row=3, column=2, sticky=Tk.W+Tk.E, ipadx=0, padx=0)
TextCrossLabel = Tk.Label(root, text=' x ', width=5, justify='center')
TextCrossLabel.grid(row=3, column=3, sticky=Tk.W+Tk.E, ipadx=0)
TextHeightEntry = Tk.Entry(root, width=10, justify='center')
TextHeightEntry.insert(0, '120')
TextHeightEntry.grid(row=3, column=4, sticky=Tk.W+Tk.E, ipadx=0, padx=0)
TextSizeLabel = Tk.Label(root, text='Font size', width=5)
TextSizeLabel.grid(row=3, column=5, sticky=Tk.W+Tk.E, ipadx=0)
TextSizeEntry = Tk.Entry(root, width=5, justify='center')
TextSizeEntry.insert(0, '96')
TextSizeEntry.grid(row=3, column=6, sticky=Tk.W+Tk.E, ipadx=0, padx=0)
def FontColorChooser():
    global textRGB
    colors=askcolor('#%02x%02x%02x' % (textRGB[0],textRGB[1],textRGB[2]), title='Choose Font Color')
    textRGB[0] = colors[0][0]
    textRGB[1] = colors[0][1]
    textRGB[2] = colors[0][2]
    FontColorButton.configure(bg=colors[1])
FontColorButton=Tk.Button(root, text='Color', fg='white', bg='#A0A0A0',  command=FontColorChooser)
FontColorButton.grid(row=3, column=7, sticky=Tk.W+Tk.E)


PositionLabel = Tk.Label(root, text='Lyric Start Position x[0-1]=', width=15)
PositionLabel.grid(row=4, column=0, columnspan=2, sticky=Tk.W+Tk.E, ipadx=0)
XPosEntry = Tk.Entry(root, width=10, justify='center')
XPosEntry.insert(0, '0.5')
XPosEntry.grid(row=4, column=2, sticky=Tk.W+Tk.E, ipadx=0, padx=0)
YPosLabel = Tk.Label(root, text='y[0-1]=', width=5, justify='right')
YPosLabel.grid(row=4, column=3, sticky=Tk.W+Tk.E, ipadx=0)
YPosEntry = Tk.Entry(root, width=10, justify='center')
YPosEntry.insert(0, '0.1')
YPosEntry.grid(row=4, column=4, sticky=Tk.W+Tk.E, ipadx=0, padx=0)

TrajectionLabel = Tk.Label(root, text='Lyric Trajectory Vector x=', width=15)
TrajectionLabel.grid(row=5, column=0, columnspan=2, sticky=Tk.W+Tk.E, ipadx=0)
XVelEntry = Tk.Entry(root, width=10, justify='center')
XVelEntry.insert(0, '0.5')
XVelEntry.grid(row=5, column=2, sticky=Tk.W+Tk.E, ipadx=0, padx=0)
YVelLabel = Tk.Label(root, text='Vector y=', width=5, justify='right')
YVelLabel.grid(row=5, column=3, sticky=Tk.W+Tk.E, ipadx=0)
YVelEntry = Tk.Entry(root, width=10, justify='center')
YVelEntry.insert(0, '2.5')
YVelEntry.grid(row=5, column=4, sticky=Tk.W+Tk.E, ipadx=0, padx=0)
GravLabel = Tk.Label(root, text='Gravity Scale [0-1]', width=10, justify='center')
GravLabel.grid(row=5, column=5, sticky=Tk.W+Tk.E, ipadx=0)
GravEntry = Tk.Entry(root, width=10, justify='center')
GravEntry.insert(0, '0.2')
GravEntry.grid(row=5, column=6, sticky=Tk.W+Tk.E, ipadx=0, padx=0)

VideoLabel = Tk.Label(root, text='Video Max. Length t[sec]=', width=15)
VideoLabel.grid(row=6, column=0, columnspan=2, sticky=Tk.W+Tk.E, ipadx=0)
MaxTEntry = Tk.Entry(root, width=10, justify='center')
MaxTEntry.insert(0, '90')
MaxTEntry.grid(row=6, column=2, sticky=Tk.W+Tk.E, ipadx=0, padx=0)
FPSLabel = Tk.Label(root, text='FPS=', width=5, justify='right')
FPSLabel.grid(row=6, column=3, sticky=Tk.W+Tk.E, ipadx=0)
FPSEntry = Tk.Entry(root, width=10, justify='center')
FPSEntry.insert(0, '30')
FPSEntry.grid(row=6, column=4, sticky=Tk.W+Tk.E, ipadx=0, padx=0)




ttfontname = "c:\\Windows\\Fonts\\meiryob.ttc"
fontsize = 72
Width = 1280
Height = 720
TextImageW = 200
TextImageH = 100

MainCanvasSize = (Width, Height)
backgroundRGB = [0,255,0, 255]
textRGB = [128,128,128,255]
MainImg = Image.new('RGBA', MainCanvasSize, tuple(backgroundRGB))
MainDraw = ImageDraw.Draw(MainImg)
font = ImageFont.truetype(ttfontname, fontsize)
TextCanvasSize= (TextImageW, TextImageH)
TextImg = Image.new('RGBA', TextCanvasSize, (255,255,255,0))
TextDraw = ImageDraw.Draw(TextImg)

idxFrame = 0
fps = 30
maxSeconds = 90
gravity=-9.8*0.2

# ImageLabel = Tk.Label(root, bg='white', fg='black', borderwidth=1, relief="solid")
ImageLabel = Tk.Label(root)
ImageLabel.grid(row=7, column=0, columnspan=8, sticky=Tk.NW+Tk.SE)
Disp_img = MainImg.resize((int(Width/2),int(Height/2)))
imgtk = ImageTk.PhotoImage(image=Disp_img)
ImageLabel.imgtk = imgtk
ImageLabel.configure(image=imgtk)

CurrentFrameSec=0
def ShowFrame(position):
    global fFileLoaded
    if(fFileLoaded==0):
        return
    global ttfontname, Lyrics, font, backgroundRGB, textRGB, maxNotes, CurrentFrameSec
    if(float(position) <= CurrentFrameSec):
        FrameScale.set(CurrentFrameSec)
        FrameScale.update()
        return
    CurrentFrameSec=float(position)
    fontsize = int(TextSizeEntry.get())
    Width = int(WidthEntry.get())
    Height = int(HeightEntry.get())
    TextImageW = int(TextWidthEntry.get())
    TextImageH = int(TextHeightEntry.get())
    
    MainCanvasSize = (Width, Height)
    MainImg = Image.new('RGBA', MainCanvasSize, tuple(backgroundRGB))
    MainDraw = ImageDraw.Draw(MainImg)
    font = ImageFont.truetype(ttfontname, fontsize)
    
    TextCanvasSize= (TextImageW, TextImageH)
    TextImg = Image.new('RGBA', TextCanvasSize, (255,255,255,0))
    TextDraw = ImageDraw.Draw(TextImg)
    TextDraw.text((0, 0), Lyrics[0], fill=tuple(textRGB), font=font)
    maskBackground = (255,255,255,0)
    MaskImg = Image.new('RGBA', TextCanvasSize, maskBackground)
    MaskDraw = ImageDraw.Draw(MaskImg)
    maskRGB= (0, 0, 0, 255)
    MaskDraw.text((0, 0), Lyrics[0], fill=maskRGB, font=font)

    fps = 10
    gravity=-9.8*float(GravEntry.get())
    
    MainDraw.rectangle((0,0, Width, Height), fill=tuple(backgroundRGB))
    for i in range(maxNotes):
        if((Seconds[i]>float(position)-5)*(Seconds[i]<float(position)+5)):
            if(LyricPosition[i, 1]>0):
                TextDraw.text((0, 0), Lyrics[i], fill=tuple(textRGB), font=font)
                MaskDraw.text((0, 0), Lyrics[i], fill=maskRGB, font=font)
                X = int(LyricPosition[i, 0]*Width)
                Y = int(Height*(1 - LyricPosition[i, 1]))
                MainImg.paste(TextImg, (X, Y, X+TextImageW, Y+TextImageH), MaskImg)
                TextDraw.rectangle((0,0, TextImageW, TextImageH), fill=tuple(backgroundRGB))
                MaskDraw.rectangle((0,0, TextImageW, TextImageH), fill=maskBackground)
                LyricVelocity[i, 1] += gravity*float(1/fps)
                LyricPosition[i, 0] += LyricVelocity[i, 0]*float(1/fps)
                LyricPosition[i, 1] += LyricVelocity[i, 1]*float(1/fps)
    Disp_img = MainImg.resize((int(Width/2),int(Height/2)))
    imgtk = ImageTk.PhotoImage(image=Disp_img)
    ImageLabel.imgtk = imgtk
    ImageLabel.configure(image=imgtk)

def InitializeLyricsMotion():
    global fFileLoaded
    if(fFileLoaded==0):
        return
    global LyricPosition, LyricVelocity, maxNotes
    LyricPosition = np.zeros((maxNotes, 2), np.float32)
    LyricVelocity = np.zeros((maxNotes, 2), np.float32)
    XPos = float(XPosEntry.get())
    YPos = float(YPosEntry.get())
    XVel = float(XVelEntry.get())
    YVel = float(YVelEntry.get())
    for i in range(maxNotes):
        LyricPosition[i, 0] = XPos
        LyricPosition[i, 1] = YPos
        LyricVelocity[i, 0] = XVel*(Beats[i]/4.0 - XPos)
        LyricVelocity[i, 1] = YVel*(float(Keyboards[i])/88.0)
        print('index=%04d: %s at position (%3.2f, %3.2f) with vector (%3.2f, %3.2f)' 
              % (i, Lyrics[i], LyricPosition[i, 0], LyricPosition[i, 1], LyricVelocity[i, 0], LyricVelocity[i, 1]))
    FrameScale.set(0)
    global CurrentFrameSec, MainDraw
    CurrentFrameSec=0
    FrameScale.configure(to=float(MaxTEntry.get()))
    MainDraw.rectangle((0,0, Width, Height), fill=tuple(backgroundRGB))
    Disp_img = MainImg.resize((int(Width/2),int(Height/2)))
    imgtk = ImageTk.PhotoImage(image=Disp_img)
    ImageLabel.imgtk = imgtk
    ImageLabel.configure(image=imgtk)
ScaleReset=Tk.Button(root, text='Reset', command=InitializeLyricsMotion)
ScaleReset.grid(row=8, column=0,sticky=Tk.W+Tk.E)
FrameScale = Tk.Scale(root, orient='horizontal', command=ShowFrame, cursor='arrow', \
                      from_=0, to=maxSeconds, resolution=0.1)
FrameScale.set(0)
FrameScale.grid(row=8,column=1, columnspan=7,sticky='ew')

def GenerateMP4():
    global fFileLoaded
    if(fFileLoaded==0):
        return
    global ttfontname, Lyrics, font, backgroundRGB, textRGB, InputFileName
    fontsize = int(TextSizeEntry.get())
    Width = int(WidthEntry.get())
    Height = int(HeightEntry.get())
    TextImageW = int(TextWidthEntry.get())
    TextImageH = int(TextHeightEntry.get())
    
    MainCanvasSize = (Width, Height)
    MainImg = Image.new('RGBA', MainCanvasSize, tuple(backgroundRGB))
    MainDraw = ImageDraw.Draw(MainImg)
    font = ImageFont.truetype(ttfontname, fontsize)
    
    TextCanvasSize= (TextImageW, TextImageH)
    TextImg = Image.new('RGBA', TextCanvasSize, (255,255,255,0))
    TextDraw = ImageDraw.Draw(TextImg)
    TextDraw.text((0, 0), Lyrics[0], fill=tuple(textRGB), font=font)
    maskBackground = (255,255,255,0)
    MaskImg = Image.new('RGBA', TextCanvasSize, maskBackground)
    MaskDraw = ImageDraw.Draw(MaskImg)
    maskRGB= (0, 0, 0, 255)
    MaskDraw.text((0, 0), Lyrics[0], fill=maskRGB, font=font)

    idxFrame = 0
    fps = float(FPSEntry.get())
    maxSeconds = float(MaxTEntry.get())
    gravity=-9.8*float(GravEntry.get())
    
    pathParent = Path(InputFileName).parent.absolute()
    MP4FileName = InputFileName.replace(".musicxml", ".mp4")
    while(float(idxFrame/fps)<maxSeconds):
        for i in range(maxNotes):
            if(float(idxFrame/fps)>Seconds[i]):
                if(LyricPosition[i, 1]>0):
                    TextDraw.text((0, 0), Lyrics[i], fill=tuple(textRGB), font=font)
                    MaskDraw.text((0, 0), Lyrics[i], fill=maskRGB, font=font)
                    X = int(LyricPosition[i, 0]*Width)
                    Y = int(Height*(1 - LyricPosition[i, 1]))
                    MainImg.paste(TextImg, (X, Y, X+TextImageW, Y+TextImageH), MaskImg)
                    TextDraw.rectangle((0,0, TextImageW, TextImageH), fill=tuple(backgroundRGB))
                    MaskDraw.rectangle((0,0, TextImageW, TextImageH), fill=maskBackground)
                    LyricVelocity[i, 1] += gravity*float(1/fps)
                    LyricPosition[i, 0] += LyricVelocity[i, 0]*float(1/fps)
                    LyricPosition[i, 1] += LyricVelocity[i, 1]*float(1/fps)
        OutFileName= '%s\\temp\\LyricImage%05d.png' % (pathParent, idxFrame)
        MainImg.save(OutFileName)
        MainDraw.rectangle((0,0, Width, Height), fill=tuple(backgroundRGB))
        ProgressLabel.configure(text='%d' % int(idxFrame/fps))
        ProgressLabel.update()
        idxFrame += 1
    CommandStr = 'ffmpeg.exe -y -r 30 -i %s' % pathParent + '\\temp\\LyricImage%05d.png -c:v libx265 -r 30 -pix_fmt yuv420p ' + MP4FileName
    subprocess.call(CommandStr, shell=True)
    CommandStr='del %s\\temp\\*.png' % pathParent
    subprocess.call(CommandStr, shell=True)
    ProgressLabel.configure(text='Finished')
    ProgressLabel.update()
ConvertButton = Tk.Button(root, text='Generate MP4 File',  command=GenerateMP4)
ConvertButton.grid(row=10, column=0, columnspan=7, sticky=Tk.W+Tk.E)
ProgressLabel=Tk.Label(root, text='', width= 10)
ProgressLabel.grid(row=10, column=7)


root.mainloop()
