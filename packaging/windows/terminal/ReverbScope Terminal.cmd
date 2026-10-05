@echo off
rem ReverbScope Terminal Edition: a Command Prompt in this folder, with the
rem reverbscope command ready. Double-clicking reverbscope.exe itself would close
rem its window as soon as it has printed the overview.
cd /d "%~dp0"
title ReverbScope Terminal Edition
cmd /k reverbscope.exe
