' InkyPi Background Sync Launcher
' Runs pc_sync.ps1 from this folder with no console window.
' To start it at sign-in, put a shortcut to this file in shell:startup.

Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

strScriptPath = fso.BuildPath(fso.GetParentFolderName(WScript.ScriptFullName), "pc_sync.ps1")

' Run the command with 0 (Hidden window) and False (Do not wait for completion)
WshShell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File " & Chr(34) & strScriptPath & Chr(34), 0, False

Set WshShell = Nothing
Set fso = Nothing
