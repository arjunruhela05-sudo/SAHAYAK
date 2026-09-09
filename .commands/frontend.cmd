@echo off
title SAHAYAK frontend (Vite)
call "C:\Users\divya\anaconda3\condabin\conda.bat" activate sahayak
cd /d "D:\CODES\sahayak2\SAHAYAK\SAHAYAK-main\frontend"
call npm run dev -- --port 5173 --strictPort
echo.
echo Frontend stopped. Press any key to close.
pause >nul
