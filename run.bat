@echo off
REM ===========================================================================
REM  Asteroid mining profitability pipeline -- Windows launcher.
REM
REM  FOR THE DASHBOARD, DOUBLE-CLICK Dashboard.vbs INSTEAD. It opens the UI
REM  in your browser with no console window at any point -- which a .bat
REM  cannot do, because cmd creates the window before the first line runs.
REM
REM  This file is the TERMINAL entry point: a menu when double-clicked, or
REM  an argument to skip straight to one option:
REM
REM      run.bat ui         open the dashboard (hands off to Dashboard.vbs
REM                         and closes this window)
REM      run.bat quick      400-row sample, all four stages
REM      run.bat rerun      Stage 4 only, against the catalogs already on disk
REM      run.bat standard   20,000-row sample, Stage 4 only
REM      run.bat full       the pipeline's own defaults (1.6 to 3.8 h)
REM      run.bat verify     run verify.py against the committed baseline
REM      run.bat build      rebuild master.py from modules/
REM      run.bat help       run_pipeline.py --help
REM
REM  A run option takes the destination as an optional second argument,
REM  so a scripted run never has to answer a prompt:
REM
REM      run.bat rerun leo
REM
REM  With no second argument it uses cislunar, the model's best case.
REM  Launched from the menu it asks instead.
REM
REM  It is a launcher and nothing more: every run goes through run_pipeline.py
REM  or ui.py, which go through master.py. No model behaviour lives here.
REM ===========================================================================

setlocal EnableDelayedExpansion
cd /d "%~dp0"

REM  Saved because inside a `call :label` routine %1 means the CALL's argument,
REM  not the batch's. ARG1 is also what tells the routines they are running
REM  scripted rather than from the menu.
set "ARG1=%~1"
set "ARG2=%~2"

REM  Scripted runs must not stop on a question -- the same rule as
REM  :ask_destination, applied to run_pipeline.py's two confirmations. It
REM  refuses rather than hangs when stdin is not a terminal, so without this
REM  a scheduled `run.bat quick` would exit 1 having done nothing, and this
REM  file's own header promises it can be scheduled.
REM
REM  The confirmations exist to catch an INCIDENTAL run -- someone testing
REM  something else who did not realise Stages 1-3 re-fetch and overwrite.
REM  Typing `run.bat quick` is not incidental, so answering for it is right.
set "YES="
if defined ARG1 set "YES=--yes"

REM  A double-click from Explorer passes NO arguments, so "was an argument
REM  given" is the whole test for interactive-vs-scripted, and it needs no
REM  guesswork. The menu path pauses so the window does not vanish; an
REM  argument path never pauses and exits with the pipeline's real code, so
REM  `run.bat quick` can be scheduled. (A %cmdcmdline% heuristic was tried
REM  first and false-positived on `cmd /c run.bat quick`, which would hang a
REM  scheduled job forever on a prompt nobody is there to answer.)

REM  The pipeline's own output is pure ASCII, so this is belt and braces
REM  rather than the fix: it covers tqdm, exception text and any data value
REM  that reaches stdout. PYTHONUTF8 cannot move an output byte -- every CSV
REM  is written by pandas to_csv, which is UTF-8 regardless of locale.
chcp 65001 >nul 2>&1
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

REM -- Find an interpreter -----------------------------------------------------
REM  `py` is the Windows launcher and the one this repo documents. A bare
REM  `python` hits the Microsoft Store alias and fails, so it is only a
REM  fallback and is verified before use.
set "PY="
py -3 -c "import sys" >nul 2>&1 && set "PY=py -3"
if not defined PY (
  python -c "import sys" >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo.
  echo   Python was not found.
  echo.
  echo   Install Python 3.11 or newer from https://www.python.org/downloads/
  echo   and tick "Add python.exe to PATH" in the installer.
  echo.
  pause
  exit /b 1
)

REM -- Check the pipeline's dependencies --------------------------------------
%PY% -c "import requests,pandas,numpy,yfinance,tqdm,pyarrow" >nul 2>&1
if errorlevel 1 (
  echo.
  echo   Some required packages are missing:
  echo     requests  pandas  numpy  yfinance  tqdm  pyarrow
  echo.
  set /p "INSTALL=  Install them now? [Y/n] "
  if /i "!INSTALL!"=="n" (
    echo   Cannot run without them. Exiting.
    pause
    exit /b 1
  )
  echo.
  %PY% -m pip install -r requirements.txt
  if errorlevel 1 (
    echo.
    echo   Install failed. Try running this from a terminal to see why.
    pause
    exit /b 1
  )
)

REM -- Dispatch on an argument, if there is one --------------------------------
if not "%~1"=="" (
  set "CHOICE=%~1"
  goto dispatch
)

set "TRIES=0"
:menu
cls
echo.
echo  ========================================================================
echo    ASTEROID MINING PROFITABILITY PIPELINE
echo  ========================================================================
echo.
echo    [1]  Dashboard              open the UI in a browser  (recommended)
echo                                closes this window - no terminal stays up
echo.
echo    [2]  Quick run              all four stages, 400-row sample
echo                                (first run downloads ~500 MB)
echo    [3]  Quick re-run           Stage 4 only, reuses catalogs on disk
echo    [4]  Standard run           Stage 4 only, 20,000-row sample
echo    [5]  Full run               THE PIPELINE DEFAULTS - every row,
echo                                beneficiated, programme search on
echo                                *** 1.6 h cislunar, 3.8 h default ***
echo.
echo         2-4 override those defaults so a run finishes in reasonable
echo         time. Every run prints each setting marked [default], or
echo         [default: ...] naming the default it replaced.
echo.
echo    [6]  Verify                 check this build against the baseline
echo    [7]  Rebuild master.py      after editing anything in modules/
echo    [8]  Command-line help
echo.
echo    [Q]  Quit
echo.
set "CHOICE="
set /p "CHOICE=  Choose: "
REM  Strip stray spaces. Harmless for every choice here (all one token), and it
REM  is what makes a piped `echo q` match -- echo appends a trailing space.
if defined CHOICE set "CHOICE=!CHOICE: =!"

:dispatch
if /i "%CHOICE%"=="1"        goto ui
if /i "%CHOICE%"=="ui"       goto ui
if /i "%CHOICE%"=="2"        goto quick
if /i "%CHOICE%"=="quick"    goto quick
if /i "%CHOICE%"=="3"        goto rerun
if /i "%CHOICE%"=="rerun"    goto rerun
if /i "%CHOICE%"=="4"        goto standard
if /i "%CHOICE%"=="standard" goto standard
if /i "%CHOICE%"=="5"        goto full
if /i "%CHOICE%"=="full"     goto full
if /i "%CHOICE%"=="6"        goto verify
if /i "%CHOICE%"=="verify"   goto verify
if /i "%CHOICE%"=="7"        goto build
if /i "%CHOICE%"=="build"    goto build
if /i "%CHOICE%"=="8"        goto clihelp
if /i "%CHOICE%"=="help"     goto clihelp
if /i "%CHOICE%"=="q"        exit /b 0
if /i "%CHOICE%"=="quit"     exit /b 0
REM  An unrecognised ARGUMENT must never reach the menu. Falling through to
REM  it puts `set /p` in front of a stdin that a scheduled job holds open and
REM  never writes to, and cmd waits there forever -- a hang, not a failure,
REM  which is the worse of the two. Same rule as :ask_destination: if an
REM  argument was given, nothing may prompt.
if defined ARG1 (
  echo.
  echo   "%CHOICE%" is not one of the options.
  echo.
  echo   Try one of:  ui  quick  rerun  standard  full  verify  build  help
  echo   or run this with no arguments for the menu.
  exit /b 1
)

REM  The menu path CAN prompt, but is bounded so a redirected stdin cannot
REM  spin it forever: `set /p` reads EOF, matches nothing, and comes straight
REM  back round. Five is plenty for a human and finite for a pipe.
set /a TRIES+=1
echo   "%CHOICE%" is not one of the options.
if %TRIES% GEQ 5 (
  echo   Giving up after five. Run `run.bat help` for the flags.
  exit /b 1
)
timeout /t 2 >nul 2>&1
goto menu

REM ---------------------------------------------------------------------------
:ui
REM  Hand the dashboard to the windowless launcher and get out of the way.
REM  That launcher exists so no console stays open while the dashboard is
REM  up, so this must NOT pause or return to the menu: either would leave
REM  behind exactly the terminal it removes. It puts up its own small
REM  window, which is what you close to stop the server.
REM
REM  Streamlit is checked THERE rather than here, because Dashboard.vbs
REM  never runs this file -- a check in this branch would cover one of the
REM  two ways in and look like it covered both.
REM  Handed to Dashboard.vbs rather than started here, so there is ONE
REM  windowless-start implementation and both entry points get the same
REM  behaviour. It is also the only form that does not block a redirected
REM  caller: a process started by `start` INHERITS this console's stdout,
REM  so `run.bat ui > log` or `run.bat ui | tee` sat there until the
REM  dashboard was closed -- while looking perfectly fine from a console.
REM  Windows Script Host's Run does not pass our handles to the process it
REM  creates, so going through it closes the pipe. (Measured: 120 s+ hang
REM  under a pipe before, 0.46 s after.) Same family as the `set /p` hang
REM  documented below -- fine interactively, broken everywhere else.
if not exist "Dashboard.vbs" (
  echo.
  echo   Dashboard.vbs is missing, so this falls back to a foreground
  echo   server. Close this window, or press Ctrl-C, to stop it.
  echo.
  %PY% -m streamlit run ui.py
  goto done
)
echo.
echo   Opening the dashboard. It appears in your browser, and a small
echo   control window lets you stop it. This window closes now.
echo.
start "" wscript.exe Dashboard.vbs
exit /b 0

REM ---------------------------------------------------------------------------
:quick
call :ask_destination
%PY% run_pipeline.py --preset quick --destination !DEST! !YES!
goto done

:rerun
call :ask_destination
%PY% run_pipeline.py --preset quick --stages 4 --destination !DEST! !YES!
goto done

:standard
call :ask_destination
%PY% run_pipeline.py --preset standard --stages 4 --destination !DEST! !YES!
goto done

:full
call :ask_destination
echo.
echo   THE PIPELINE DEFAULTS: every one of 1.55 million rows, beneficiated,
echo   with the programme search on. This preset overrides nothing -- it is
echo   what a configure-nothing run does. Measured 2026-08-24: Stage 4 alone
echo   is 1.6 h at cislunar and 3.8 h at earth_surface, the config default.
echo   Budget half a day if Stages 1-3 run too.
echo.
echo   Ctrl-C is safe. Each stage writes its CSV before the next one starts.
echo.
%PY% run_pipeline.py --preset full --destination !DEST! !YES!
goto done

:verify
REM  verify.py defaults to `--tag head`, and there is no baseline-head -- so
REM  check 1 would compare against nothing and say so in one line nobody
REM  reads, silently turning the most important of the six into a hash print.
REM  Use the newest baseline actually on disk. /o-d sorts newest first.
set "TAG="
for /f "delims=" %%d in ('dir /b /ad /o-d ".verify\baseline-*" 2^>nul') do (
  if not defined TAG set "TAG=%%d"
)
echo.
if defined TAG (
  set "TAG=!TAG:baseline-=!"
  echo   Comparing against baseline "!TAG!".
) else (
  echo   No baseline under .verify\ -- check 1 has nothing to compare
  echo   against, so it reports NOT VERIFIED and exits 1. That is not
  echo   a failure of this build: checks 2-6 still run and still count.
  echo.
  echo   To make one, run this on a CLEAN tree BEFORE editing anything:
  echo       py verify.py baseline --tag mytag
)
echo.
echo   A full check builds ~20 cells and takes about half an hour.
echo   This skips checks 2 and 3 to run in ~5 minutes, and still catches
echo   any change to any number. Drop --skip before committing.
echo.
if defined TAG (
  %PY% verify.py check --tag !TAG! --skip prune parallel
) else (
  %PY% verify.py check --skip prune parallel
)
goto done

:build
%PY% build_master.py
echo.
echo   Reminder: commit master.py together with the modules it was built from.
echo   `git status` immediately after a build is the sync check.
goto done

:clihelp
%PY% run_pipeline.py --help
goto done

REM ---------------------------------------------------------------------------
REM  Stage 2 decides what a kilogram sells for and Stage 4 decides the
REM  architecture that puts it there. They MUST agree, so one prompt sets
REM  both -- run_pipeline.py writes them through MASTER_CONFIG together.
REM  cislunar is the default because it is the model's best case and the
REM  destination the catalog on disk is normally priced for.
:ask_destination
REM  A scripted run must not prompt. It takes the destination as the second
REM  argument (`run.bat rerun leo`) and otherwise defaults, because `set /p`
REM  against a redirected or absent stdin reads EOF, leaves the prompt
REM  unanswered and makes cmd exit 255 -- so a scheduled `run.bat quick` would
REM  report failure on a run that in fact succeeded.
REM
REM  Tested BEFORE the menu is echoed, so a scripted run does not log a prompt
REM  it never asks. Choosing a destination the Stage 2 catalog on disk was not
REM  priced for is caught by run_pipeline.py, which refuses before the run
REM  starts rather than producing meaningless numbers.
if defined ARG1 (
  set "DEST=cislunar"
  if not "%ARG2%"=="" set "DEST=%ARG2%"
  exit /b 0
)

echo.
echo   Where is the material sold?
echo     [1] cislunar  (default -- the best case)   [2] lunar_surface
echo     [3] leo                                    [4] mars_surface
echo     [5] earth_surface                          [6] mars_orbit
echo     [7] geo

REM  Written as "default, then override" rather than one `if` per branch with
REM  an `& exit` on the end: in batch, `if cond A & B` runs B UNCONDITIONALLY,
REM  so that form exits after the first test and every choice but the first
REM  falls through with DEST unset.
set "D="
set /p "D=  Choose [1]: "
set "DEST=cislunar"
if "%D%"=="2" set "DEST=lunar_surface"
if "%D%"=="3" set "DEST=leo"
if "%D%"=="4" set "DEST=mars_surface"
if "%D%"=="5" set "DEST=earth_surface"
if "%D%"=="6" set "DEST=mars_orbit"
if "%D%"=="7" set "DEST=geo"
exit /b 0

REM ---------------------------------------------------------------------------
:done
REM  Captured on the FIRST line: any echo in between would reset errorlevel.
set "RC=%errorlevel%"
echo.
if "%~1"=="" (
  REM  Came from the menu, so there is a menu to go back to.
  pause
  goto menu
)
exit /b %RC%
