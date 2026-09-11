@echo off
REM ---------------------------------------------------------------------------
REM Launch the campaign queue DETACHED from any agent or terminal session.
REM
REM The 2026-09-09 start died here: the queue was a child of the agent shell, so
REM session teardown killed it with rc=1073807364 (STATUS_CONTROL_C_EXIT) two
REM hours into cell 4, and nothing ran for two days.  A campaign measured in
REM days must outlive the thing that started it, so this is run through Task
REM Scheduler (schtasks), which parents it to the scheduler service instead.
REM
REM The interpreter is spelled out rather than left as `py`: CLAUDE.md records
REM this machine carrying two registered installs of one Python minor version,
REM where `py` reached one and the dashboard's dependencies were in the other.
REM If it ever moves, re-run the generator that wrote this file rather than
REM editing the path by hand.
REM ---------------------------------------------------------------------------
cd /d "C:\Users\Owner\OneDrive\Documents\GitHub\economicspace"

if not exist "C:\Users\Owner\AppData\Local\Programs\Python\Python313\python.exe" (
  echo CAMPAIGN LAUNCH FAILED: interpreter not found at "C:\Users\Owner\AppData\Local\Programs\Python\Python313\python.exe" >> campaign\logs\_queue.log
  exit /b 9
)

echo. >> campaign\logs\_queue.log
echo ===== detached queue start %DATE% %TIME% ===== >> campaign\logs\_queue.log
"C:\Users\Owner\AppData\Local\Programs\Python\Python313\python.exe" campaign\run_queue.py >> campaign\logs\_queue.log 2>&1
