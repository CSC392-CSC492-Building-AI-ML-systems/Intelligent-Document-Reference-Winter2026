#!/usr/bin/env python3
"""Standalone file picker using tkinter. Prints chosen file paths to stdout (one per line) or nothing if cancelled.
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
    file_paths = filedialog.askopenfilenames(
        initialdir=initial_dir, title="Select files"
    )
    root.destroy()

    if file_paths:
        for fp in file_paths:
            print(os.path.abspath(os.path.realpath(fp)))
    sys.exit(0)


if __name__ == "__main__":
    main()
