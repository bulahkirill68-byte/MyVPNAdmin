Unicode true
!include "LogicLib.nsh"
!include "FileFunc.nsh"
Name "Reality VPN ${VERSION}"
OutFile "${OUTPUT_FILE}"
Icon "${ICON_FILE}"
RequestExecutionLevel user
CRCCheck off
SetCompressor /SOLID zlib
AutoCloseWindow true
ShowInstDetails nevershow
Caption "Reality VPN — подготовка первого запуска"
Page instfiles
Var LockHandle
Var CommandArgs
Function .onInit
  StrCpy $INSTDIR "$LOCALAPPDATA\RealityVPNClient\portable\${BUILD_KEY}"
  System::Call 'kernel32::CreateMutexW(p 0, i 0, w "Local\RealityVPNPortable-${BUILD_KEY}") p .r0'
  StrCpy $LockHandle $0
  System::Call 'kernel32::WaitForSingleObject(p r0, i 120000) i .r1'
  ${If} $1 != 0
  ${AndIf} $1 != 128
    MessageBox MB_ICONSTOP "Не удалось дождаться подготовки Reality VPN. Повторите запуск."
    Quit
  ${EndIf}
  IfFileExists "$INSTDIR\.ready" 0 prepare
  IfFileExists "$INSTDIR\Reality VPN.exe" 0 prepare
  IfFileExists "$INSTDIR\resources\app.asar" 0 prepare
  IfFileExists "$INSTDIR\resources\native\RuntimeControl.exe" 0 prepare
  IfFileExists "$INSTDIR\resources\engine\xray.exe" 0 prepare
  SetSilent silent
  Goto done
prepare:
  Delete "$INSTDIR\.ready"
  SetSilent normal
done:
FunctionEnd
Section
  IfFileExists "$INSTDIR\.ready" cached
  SetDetailsPrint textonly
  DetailPrint "Однократная подготовка. Следующие запуски — без распаковки."
  SetOutPath "$INSTDIR"
  ClearErrors
  File /r "${APP_DIR}\*.*"
  ${If} ${Errors}
    MessageBox MB_ICONSTOP "Не удалось распаковать Reality VPN. Проверьте свободное место и доступ к папке."
    Abort
  ${EndIf}
  FileOpen $0 "$INSTDIR\.ready" w
  FileWrite $0 "${BUILD_KEY}"
  FileClose $0
cached:
  System::Call 'kernel32::ReleaseMutex(p $LockHandle)'
  System::Call 'kernel32::CloseHandle(p $LockHandle)'
  System::Call 'kernel32::SetEnvironmentVariableW(w "PORTABLE_EXECUTABLE_DIR", w "$EXEDIR")'
  System::Call 'kernel32::SetEnvironmentVariableW(w "PORTABLE_EXECUTABLE_FILE", w "$EXEPATH")'
  ${GetParameters} $CommandArgs
  SetOutPath "$INSTDIR"
  Exec '"$INSTDIR\Reality VPN.exe" $CommandArgs'
  ${If} ${Errors}
    MessageBox MB_ICONSTOP "Не удалось запустить Reality VPN."
    SetErrorLevel 1
  ${EndIf}
SectionEnd
