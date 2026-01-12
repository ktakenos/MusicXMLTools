# Tools for musicxml files

## Scropts and their functions

**tab_highway_xml.py**

This code is CLI python script.
This script reads musicxml file with lyrics, and generates a video of your character singing.
It requires 4 png files for three vowels, A, O, and U, and N for closed mouth. They should be stored in the working directory.
This script is built using chatGPT.



**tab_highway_xml.py**

This code is CLI python script
This script reads musicxml file with Guitar/Base Tab notes, and generates a video of the tab roll like piano roll, which may be call tab highway.
This script is built using chatGPT.

**GPT_Tab_CanvasUI.py**


**Musicxml2TabJSON.py**


**GPT-apply_lyrics.py**



**MusicxmlLyric2MP4.py**

This code runs on python Tkinter
This code converts lyric texts to a mp4 movie where those syllabic texts fly from right to left at their determined beats.
The musicxml files must have the vocal part only with syllabic texts on each note.


**Musicxmlpart2FretboardChart.py**

This code runs on python Tkinter
This code converts a guitar part to a fretboard chart that plays the part and also shows fretboard chart of the playing note. Optionally it converts the fretboard chart to a MP4 movie.
The musicxml files must have a single musical instrument part only.


## Examples

Using code **MusicxmlLyric2MP4.py**, I made these videos for the demonstration.

[![Youtube Video](https://github.com/ktakenos/MusicXMLTools/blob/main/images/ZundamonVocal.pptx(8).jpg)](https://youtu.be/c0aQiXTqQG0)
[![Youtube Video](https://github.com/ktakenos/MusicXMLTools/blob/main/images/ZundamonVocal.pptx.jpg)](https://youtu.be/uxjGihznG0g)
[![Youtube Video](https://github.com/ktakenos/MusicXMLTools/blob/main/images/ZundamonVocal.pptx(1).jpg)](https://youtu.be/RJ6ULlNnVdg)





Using code **Musicxmlpart2FretboardChart.py**, I made this video for the demonstration.

[![Youtube Video](https://github.com/ktakenos/MusicXMLTools/blob/main/images/GuitarLonlinessBluePlanet-01.pptx(6).jpg)](https://youtu.be/955YI1p3Z90)





Importing libralies are the followings.

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


import pygame

import scipy.io.wavfile as wavefile

from queue import Empty, Queue

from threading import Thread


This Readme is not completed. I am working on it...

