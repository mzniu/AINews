@echo off
cd /d %~dp0..
python -m services.ingestion.worker
pause
