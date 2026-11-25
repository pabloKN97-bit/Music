"""Lanzador para PyInstaller y para ejecutar desde el código: python run_glassplayer.py"""
import sys

from glassplayer.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
