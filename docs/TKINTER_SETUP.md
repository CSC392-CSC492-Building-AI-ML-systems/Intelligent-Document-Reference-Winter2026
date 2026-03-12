# Using the folder picker (tkinter)

The **Browse** buttons in Settings (inclusion/exclusion folder) use a native folder picker powered by Python’s tkinter, which requires a Python build that includes Tcl/Tk.

If you see:

> Folder picker not available: this Python was not built with tkinter.

follow the steps below for your OS so the app uses a Python that has tkinter.

---

## macOS (Homebrew)

Your default `python3` from Homebrew is often built **without** Tcl/Tk. The formula **python-tk@3.12** adds tkinter to Homebrew’s **python@3.12**; it does **not** install its own binary. Use **`/opt/homebrew/bin/python3.12`** after installing python-tk.

### Option A: Install `python-tk` (recommended)

1. **Install Python with tkinter** (this installs python@3.12 as a dependency if needed):

   ```bash
   brew install python-tk@3.12
   ```

2. **Recreate the virtual environment** with Homebrew’s Python 3.12 (from the project root):

   ```bash
   rm -rf .venv
   /opt/homebrew/bin/python3.12 -m venv .venv
   .venv/bin/pip install -e .
   # or: uv sync (if you use uv)
   ```

3. **Run the app** with the venv’s Python:

   ```bash
   .venv/bin/python app.py --webui
   ```

   If `python3.12` is on your PATH, you can use `python3.12 -m venv .venv` instead of the full path.

### Option B: Python from python.org

1. Download the **macOS installer** from [python.org/downloads](https://www.python.org/downloads/).
   The official installer includes Tcl/Tk.

2. Install it, then recreate the venv with that Python, for example:

   ```bash
   rm -rf .venv
   /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 -m venv .venv
   .venv/bin/pip install -e .
   .venv/bin/python app.py --webui
   ```

(Adjust the path if your version or install location is different.)

---

## Linux

- **Debian/Ubuntu:**
  `sudo apt install python3-tk`
  Then use `python3` as usual (it will have tkinter). Recreate `.venv` with that `python3` if needed.

- **Fedora:**
  `sudo dnf install python3-tkinter`

After installing, recreate the venv with the same interpreter and reinstall deps if necessary.

---

## Windows

The standard Windows installers from [python.org](https://www.python.org/downloads/) usually include Tcl/Tk. During installation, ensure **"tcl/tk and IDLE"** (or similar) is enabled.

If your current install doesn’t have tkinter, reinstall Python from python.org with that option checked, then recreate `.venv` with that Python.

---

## Verify tkinter

From the project root, using the same Python that runs the app:

```bash
.venv/bin/python -c "import tkinter; print('tkinter OK')"
```

If you see `tkinter OK`, the folder picker (Browse) in Settings will work.
