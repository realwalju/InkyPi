' InkyPi Background Sync Launcher
' This script launches the batch file invisibly.

Set WshShell = CreateObject("WScript.Shell")

' Ensure this path matches where you saved pc_sync_hidden.bat
strBatchPath = "C:\PiTools\pc_sync_hidden.bat"

' Run the command with 0 (Hidden window) and False (Do not wait for completion)
WshShell.Run "cmd /c " & Chr(34) & strBatchPath & Chr(34), 0, False

Set WshShell = Nothing


start_sync.vbs
