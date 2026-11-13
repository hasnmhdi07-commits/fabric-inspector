@echo off
rem Starts the Fabric Defect Inspector floating bubble (no console window).
cd /d C:\thesis
start "" "C:\thesis\venv\Scripts\pythonw.exe" -m src.app.main
