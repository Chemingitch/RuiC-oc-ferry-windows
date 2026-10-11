OC Ferry 0.3.0 - Windows portable build
================================================

HOW TO START
  Double-click   Start OC Ferry.bat

WHY THE .bat AND NOT app\OC Ferry.exe DIRECTLY
  The launcher does two required things:
    1. Pins the data directory to .\data, so the whole folder is
       portable and uninstalling is just deleting the folder.
    2. Clears ELECTRON_RUN_AS_NODE, which a parent process may have
       injected. Without this the app can run as plain Node and
       never open a window.

LAYOUT
  app\                 main program (Electron, ~373 MB)
  data\                runtime data, created on first launch
  Start OC Ferry.bat   launcher
  README.txt           this file

FIRST RUN
  1. The app lives in the system tray; right-click the tray icon to quit.
  2. It prepares an isolated OpenCode runtime (needs network on first run)
     and opens a local OpenAI-compatible endpoint.
  3. Import models.json in WorkBuddy to see entries named "OC - <model>".

REQUIREMENTS
  - Windows 10 / 11 (x64)
  - Network access on first launch
  - WebView2 runtime (built into Windows 11 and recent Windows 10)

SOURCE & LICENSE
  Upstream: https://github.com/HRuiCcc/RuiC-oc-ferry   (MIT)
  This build: https://github.com/Chemingitch/RuiC-oc-ferry-windows
  Based on upstream v0.3.0 plus this fork's Windows changes.
