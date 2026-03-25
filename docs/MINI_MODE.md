# Mini Mode (Electron Spotlight Widget)

This project now includes an Electron-based Mini Mode shell to provide true global hotkey support and a floating quick-access widget.

## Platform Choice

Mini Mode is implemented using **Electron** (preferred architecture) because web/PWA alone cannot reliably support a global hotkey while browser is backgrounded.

## What It Does

- Global hotkey opens/closes widget: `CommandOrControl+Shift+Space`
- Frameless always-on-top overlay (`/mini` route)
- Keyboard-first interaction:
  - Up/Down navigate rows
  - Enter opens file or runs quick query
  - Escape dismisses widget
- Click outside or focus loss auto-dismisses
- `Open Full App` restores/focuses main app window

## File Map

- Electron shell:
  - `desktop/mini-mode/main.cjs`
  - `desktop/mini-mode/preload.cjs`
  - `desktop/mini-mode/package.json`
- Mini UI page:
  - `ui/src/app/pages/MiniModePage.tsx`
  - Route registered in `ui/src/app/App.tsx`
- Backend mini search API:
  - `backend/api/routes_mini.py`
  - Registered in `backend/main.py`

## Run

Start the app as usual:

```bash
python app.py --webui
```

This now auto-starts the Mini Mode Electron helper (best effort) and registers the global hotkey.
No second terminal is required.

Optional: disable helper auto-start for a web-only session:

```bash
python app.py --webui --no-mini-mode
```

## Optional Env Overrides

- `MINI_MODE_HOTKEY` (default: `CommandOrControl+Shift+Space`)
- `MINI_MODE_MAIN_URL` (default: `http://127.0.0.1:8000/chat`)
- `MINI_MODE_WIDGET_URL` (default: `http://127.0.0.1:8000/mini`)

Example:

```bash
MINI_MODE_HOTKEY="CommandOrControl+Shift+K" npm start
```

## Notes

- Mini search reads from indexed files constrained to current context files.
- Quick query uses existing `/chat/query` endpoint.
- File-open action writes `localStorage['miniMode.openFile']` and focuses main app.
