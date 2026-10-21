<#
.SYNOPSIS
  Freeze or unfreeze the running campaign without losing the in-flight cell.

.DESCRIPTION
  A campaign cell is 0.5-8 h of compute that writes NOTHING until it finishes,
  so killing the queue mid-cell throws that cell away entirely.  Suspending the
  process tree frees every core immediately and keeps the work.

  [!]  A reboot while suspended loses the in-flight cell, exactly as killing it
  would -- the queue resumes at that cell from the beginning.  Everything
  already in campaign/results.csv with rc == 0 is safe on disk either way.

  The freezing is quietqueue's pause.ps1 (campaign/quietqueue_pin.py checks
  the pin and names its path), which documents and tests it.  This file holds
  the campaign's values for its parameters: the queue's and memwatch's command
  lines, and the scheduled task whose reboot trigger tracks the pause.

.PARAMETER Resume
  Thaw instead of freeze.

.PARAMETER Match
  Command-line patterns (PowerShell -like) naming the roots of the trees to
  freeze; every descendant of a root is frozen with it.

.PARAMETER ProcessName
  The WQL LIKE pattern for the process names searched.

.PARAMETER TaskName
  The scheduled task whose reboot trigger tracks the pause.  A task this
  machine does not have leaves the scheduler alone and says so.

.EXAMPLE
  powershell -File campaign\_pause.ps1            # freeze
  powershell -File campaign\_pause.ps1 -Resume    # thaw and carry on
#>
param(
  [switch]$Resume,
  [string[]]$Match = @('*run_queue*', '*memwatch*'),
  [string]$ProcessName = 'python%',
  [string]$TaskName = 'economicspace_campaign'
)

$pin = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) 'quietqueue_pin.py'
$script = & python $pin --pause-script
if ($LASTEXITCODE -ne 0 -or -not $script) { exit 1 }   # quietqueue_pin said why
& $script -Resume:$Resume -Match $Match -ProcessName $ProcessName -TaskName $TaskName
exit $LASTEXITCODE
