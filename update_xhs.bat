@echo off
rem SG Radar - Xiaohongshu crawl + site rebuild.
rem First run: a browser window opens with a QR code -> scan it with your
rem Xiaohongshu app. Login state is saved, so later runs need no scan.
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0vendor\MediaCrawler"
".venv\Scripts\python" main.py --platform xhs --lt qrcode --type search
cd /d "%~dp0"
".venv\Scripts\python" -m src.pipeline
pause
