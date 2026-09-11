@echo off
REM Sample RSS across the campaign, detached, for the same reason as the queue.
cd /d "C:\Users\Owner\OneDrive\Documents\GitHub\economicspace"
"C:\Users\Owner\AppData\Local\Programs\Python\Python313\python.exe" campaign\memwatch.py >> campaign\logs\_memwatch.log 2>&1
