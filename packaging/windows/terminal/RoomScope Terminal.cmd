@echo off
rem RoomScope Terminal Edition: a Command Prompt in this folder, with the
rem roomscope command ready. Double-clicking roomscope.exe itself would close
rem its window as soon as it has printed the overview.
cd /d "%~dp0"
title RoomScope Terminal Edition
cmd /k roomscope.exe
