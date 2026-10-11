; Installed once, resident afterwards: the autostart entry launches the tray-only
; mode (--hidden), so the models imported into WorkBuddy stay reachable without
; the user re-opening anything. The uninstaller removes exactly this one value.

!macro customInstall
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "OC Ferry" '"$INSTDIR\OC Ferry.exe" --hidden'
  ; 预建 data 目录：应用看到它就会启用「便携模式」，把全部数据
  ; （含首次启动自动下载的 OpenCode 运行时）都放在安装目录里，
  ; 而不是 %APPDATA%。这样「装到哪，东西就在哪」。
  CreateDirectory "$INSTDIR\data"
  CreateDirectory "$INSTDIR\data\runtime"
!macroend

!macro customUnInstall
  DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Run" "OC Ferry"
!macroend
