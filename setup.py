#!/usr/bin/env python3
from distutils.core import setup
import py2exe

setup(
	console = ['dmsvg.py'],
	options = {
		"py2exe": {
			"includes": ["omg", "PIL"],
			"excludes": ["PyQt5", "PySide2", "numpy", "soundfile", "tkinter"],
			"bundle_files": 2,
			"optimize": 2,
			"compressed": True,
			"xref": True
		}
	}
)