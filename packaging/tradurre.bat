@echo off
rem Double-click launcher for Tradurre (installed with `uv tool install`).
rem Keep this window open while you work; closing it stops Tradurre.
title Tradurre
tradurre %*
if errorlevel 1 pause
