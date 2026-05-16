@echo off
echo ========================================
echo  AyumiDB Dashboard - Starting...
echo ========================================
echo.
echo Access at: http://localhost:8501
echo Close this window to stop the server.
echo.
wsl ~ -e bash -c "cd ~/ayumindb && python3 scripts/export_cookies.py 2>/dev/null && streamlit run ayumindb/app.py --server.headless true"
pause
