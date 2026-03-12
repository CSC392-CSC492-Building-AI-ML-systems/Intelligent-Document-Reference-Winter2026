#!/usr/bin/env python3
"""Standalone folder picker using tkinter. Prints chosen path to stdout (one line) or nothing if cancelled.
Run as subprocess so tkinter uses the process main thread (required on macOS)."""

import os
import sys


def main():
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        print("TKINTER_UNAVAILABLE", file=sys.stderr)
        sys.exit(1)

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    initial_dir = os.path.abspath(os.path.expanduser("~"))
    folder_path = filedialog.askdirectory(initialdir=initial_dir, title="Select folder")
    root.destroy()

    if folder_path:
        print(os.path.abspath(os.path.realpath(folder_path)))
    sys.exit(0)


if __name__ == "__main__":
    main()
