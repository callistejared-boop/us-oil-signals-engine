@echo off
cd /d "%~dp0"
:menu
cls
echo ================================================
echo    SIGNALS PLATFORM  -  START HERE
echo ================================================
echo.
echo   FIRST TIME SETUP
echo     1   Install everything  [run once]
echo     2   Verify the whole system
echo.
echo   DAILY USE
echo     3   Send a signal now
echo     4   WTI institutional note
echo     5   Command Center  [one screen for everything]
echo     6   Performance dashboard
echo     7   Live News and Bias  [BUY/SELL all pairs]
echo.
echo   INSIGHTS
echo     8   Self-review  [what predicts wins]
echo     9   Weekly self-audit to Telegram
echo    10   Refresh live news + fundamentals now
echo.
echo   AUTOMATION  [set and forget]
echo    11   Schedule 90-min briefings
echo    12   Schedule 5-min news + bias + auto-alerts
echo    13   Schedule entry scanner
echo    14   Start TradingView webhook receiver
echo    15   Fix battery / sleep interruptions
echo.
echo     0   Exit
echo.
set /p choice=Type a number then press Enter: 

if "%choice%"=="1"  call 2_INSTALL.bat & goto menu
if "%choice%"=="2"  call 7_VERIFY_ALL.bat & goto menu
if "%choice%"=="3"  call 4_SEND_SIGNAL_NOW.bat & goto menu
if "%choice%"=="4"  call G_WTI_NOTE.bat & goto menu
if "%choice%"=="5"  call I_COMMAND_CENTER.bat & goto menu
if "%choice%"=="6"  call F_DASHBOARD.bat & goto menu
if "%choice%"=="7"  call N_NEWS_INTERFACE.bat & goto menu
if "%choice%"=="8"  call H_SELF_REVIEW.bat & goto menu
if "%choice%"=="9"  call J_WEEKLY_AUDIT.bat & goto menu
if "%choice%"=="10" call K_REFRESH_FUNDAMENTALS.bat & goto menu
if "%choice%"=="11" call A_SCHEDULE_90MIN.bat & goto menu
if "%choice%"=="12" call M_SCHEDULE_NEWS_5MIN.bat & goto menu
if "%choice%"=="13" call B_SCHEDULE_ENTRY_SCAN.bat & goto menu
if "%choice%"=="14" call O_START_TV_WEBHOOK.bat & goto menu
if "%choice%"=="15" call 6_FIX_BATTERY.bat & goto menu
if "%choice%"=="0"  exit
echo.
echo Not a valid choice - try again.
timeout /t 2 >nul
goto menu
