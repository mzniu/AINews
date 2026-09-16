; Kill running AINews before overwrite (upgrade / reinstall).
; Prevents: "Error opening file for writing: ...\ainews-desktop.exe"

!macro NSIS_HOOK_PREINSTALL
  DetailPrint "Stopping any running AINews instances..."
  nsExec::Exec 'taskkill /F /T /IM ainews-desktop.exe'
  Pop $0
  nsExec::Exec 'taskkill /F /T /IM AINews.exe'
  Pop $0
  Sleep 800
  SetOverwrite on
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  DetailPrint "Stopping any running AINews instances..."
  nsExec::Exec 'taskkill /F /T /IM ainews-desktop.exe'
  Pop $0
  nsExec::Exec 'taskkill /F /T /IM AINews.exe'
  Pop $0
  Sleep 800
!macroend
