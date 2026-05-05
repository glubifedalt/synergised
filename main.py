"""
main.py – Synergy Teacher Dashboard
Run with:  python main.py
Build EXE: see BUILD.md
"""
import sys
import os

# Ensure the app directory is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main_window import run

if __name__ == "__main__":
    run()
