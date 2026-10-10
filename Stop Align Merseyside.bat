@echo off
setlocal
title Stop Align Merseyside
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*otp-shaded-2.8.0.jar*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo Local OTP server stopped if it was running.
endlocal
