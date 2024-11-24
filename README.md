# Software tools for musicxml files

## codes functions (currently only two codes)
**MusicxmlLyric2MP4.py**

This code runs on python Tkinter
This code converts lyric texts to a mp4 movie where those syllabic texts fly from right to left at their determined beats.
The musicxml files must have the vocal part only with syllabic texts on each note.


**Musicxmlpart2FretboardChart.py**

This code runs on python Tkinter
This code converts a guitar part to a fretboard chart that plays the part and also shows fretboard chart of the playing note. Optionally it converts the fretboard chart to a MP4 movie.
The musicxml files must have a single musical instrument part only.


## Examples

Using this code, I made this video for the demonstration.

[![Youtube Video](https://github.com/ktakenos/MusicXMLTools/blob/main/images/ZundamonVocal.pptx.jpg, width="360px)](https://youtu.be/uxjGihznG0g)

https://youtu.be/uxjGihznG0g
<p>
 <img src="https://github.com/ktakenos/MusicXMLTools/blob/main/images/ZundamonVocal.pptx.jpg", width="360px">
</p>


https://youtu.be/RJ6ULlNnVdg
<p>
 <img src="https://github.com/ktakenos/MusicXMLTools/blob/main/images/ZundamonVocal.pptx(1).jpg", width="360px">
</p>


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

