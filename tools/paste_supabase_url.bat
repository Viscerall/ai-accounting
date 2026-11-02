@echo off
chcp 65001 >nul
cd /d C:\Users\nizar\ai-accounting

echo ============================================
echo  PASTE CONNECTION STRING SUPABASE
echo ============================================
echo.
echo  1. Buka Supabase Dashboard -^> project AI Accounting
echo  2. Klik Connect -^> Database -^> Session Pooler
echo  3. Copy connection string
echo.
echo  Di jendela ini: klik kanan sekali = Paste
echo  (atau Ctrl+V), lalu tekan Enter.
echo.
set "MYURL="
set /p "MYURL=DATABASE_URL="

if not defined MYURL goto empty

powershell -NoProfile -Command "$u = ($env:MYURL.Trim()).Trim('\"'); if ($u -match '^postgresql://') { Set-Content -LiteralPath '.env.supabase' -Value ('DATABASE_URL=' + $u) -Encoding ascii; Write-Host '[OK] Tersimpan ke .env.supabase'; $m = (Get-Content '.env.supabase' -Raw).Trim(); Write-Host ('Target: ' + ($m -replace '//[^@]*@','//***:***@')) } else { Write-Host '[GAGAL] Text bukan connection string postgresql - tidak ada file yang diubah' -ForegroundColor Red }"

echo.
pause
exit /b 0

:empty
echo [GAGAL] Belum di-paste apa-apa - tidak ada file yang diubah
echo.
pause
exit /b 1
