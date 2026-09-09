@echo off
title SAHAYAK backend (FastAPI)
call "C:\Users\divya\anaconda3\condabin\conda.bat" activate sahayak
cd /d "D:\CODES\sahayak2\SAHAYAK\SAHAYAK-main\backend"
echo Backend starting on http://127.0.0.1:8000  (API docs: /docs)
echo First request downloads the NLP model; first video file downloads the MediaPipe models.
uvicorn main:app --host 127.0.0.1 --port 8000
echo.
echo Backend stopped. Press any key to close.
pause >nul
