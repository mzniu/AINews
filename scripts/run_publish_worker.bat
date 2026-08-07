@echo off
cd /d %~dp0..
set PUBLISH_WORKER_MODE=separate
python -m services.publishing.worker
pause
