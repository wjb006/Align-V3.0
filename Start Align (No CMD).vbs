Option Explicit

Dim shell, fso, appDir, pythonExe, launchScript, port, browserUrl
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

appDir = fso.GetParentFolderName(WScript.ScriptFullName)
pythonExe = appDir & "\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(pythonExe) Then pythonExe = "pythonw.exe"
launchScript = appDir & "\launch.py"
port = "8010"
browserUrl = "http://127.0.0.1:" & port & "/"

shell.Environment("Process")("ALIGN_BETA_MODE") = "1"
shell.Environment("Process")("ALIGN_PORT") = port

shell.CurrentDirectory = appDir
shell.Run Chr(34) & pythonExe & Chr(34) & " " & Chr(34) & launchScript & Chr(34), 0, False

' Give the local server a moment to bind before opening the browser.
WScript.Sleep 1500
shell.Run browserUrl, 1, False
