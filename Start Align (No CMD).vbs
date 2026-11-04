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

shell.Environment("Process")("ALIGN_BETA_MODE") = "0"
shell.Environment("Process")("ALIGN_STUDIO_LOCAL") = "1"
shell.Environment("Process")("ALIGN_PORT") = port

' Enable scheduled transport only when an OTP URL is configured or the
' prepared local Merseyside OTP service is already listening. Never point
' Align at a service that has not started.
Dim otpUrl, otpProbe, otpCommand
otpUrl = Trim(shell.Environment("Process")("ALIGN_OTP_URL"))
If Len(otpUrl) = 0 Then
    otpCommand = "powershell.exe -NoProfile -Command " & Chr(34) & _
        "$client=New-Object Net.Sockets.TcpClient; try { $wait=$client.BeginConnect('127.0.0.1',8080,$null,$null); " & _
        "if(-not $wait.AsyncWaitHandle.WaitOne(700)){exit 1}; $client.EndConnect($wait); exit 0 } " & _
        "catch { exit 1 } finally { $client.Dispose() }" & Chr(34)
    Set otpProbe = shell.Exec(otpCommand)
    Do While otpProbe.Status = 0
        WScript.Sleep 50
    Loop
    If otpProbe.ExitCode = 0 Then otpUrl = "http://127.0.0.1:8080/otp/gtfs/v1"
End If
If Len(otpUrl) > 0 Then
    shell.Environment("Process")("ALIGN_OTP_URL") = otpUrl
    If Len(Trim(shell.Environment("Process")("ALIGN_TRANSPORT_ENABLED"))) = 0 Then
        shell.Environment("Process")("ALIGN_TRANSPORT_ENABLED") = "1"
    End If
End If

shell.CurrentDirectory = appDir
shell.Run Chr(34) & pythonExe & Chr(34) & " " & Chr(34) & launchScript & Chr(34), 0, False

' Give the local server a moment to bind before opening the browser.
WScript.Sleep 1500
shell.Run browserUrl, 1, False
