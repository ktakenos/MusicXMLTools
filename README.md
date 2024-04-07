# Software tools for musicxml files

## codes functions (currently only one code)
** MusicxmlLyric2MP4.py
This code runs on python Tkinter

This code converts lyric texts to a mp4 movie where those syllabic texts fly from right to left at their determined beats.
The musicxml files must have the vocal part only with syllabic texts on each note.

Using this code, I made this video for the demonstration.

https://youtu.be/uxjGihznG0g
![](https://github.com/ktakenos/MusicXMLTools/blob/main/images/ZundamonVocal.pptx.jpg)
https://youtu.be/RJ6ULlNnVdg
![](https://github.com/ktakenos/MusicXMLTools/blob/main/images/ZundamonVocal.pptx(1).jpg)


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


This Readme is not completed. I am working on it...

