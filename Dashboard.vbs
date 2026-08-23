' ==========================================================================
'  Asteroid mining profitability pipeline -- double-click entry point.
'
'  Opens the dashboard in your browser. No terminal window, at any point.
'
'  This file exists only because there is no way to start a console program on
'  Windows without a console flashing up. A .bat cannot avoid it -- cmd creates
'  the window before the first line runs -- and a shortcut set to "Minimized"
'  still puts it on the taskbar. Windows Script Host is the one launcher that
'  can start a process with no window at all, which is what `sh.Run(..., 0)`
'  below does.
'
'  It is a launcher and nothing more. Every decision -- which port, whether a
'  dashboard is already up, what to do when Streamlit is missing -- lives in
'  launch_ui.py, where it can be read and tested. Keep this file dumb.
' ==========================================================================

Option Explicit

Dim fso, sh, here, target, py

Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")

' Double-clicked from Explorer, the working directory is not necessarily the
' folder this file is in -- and launch_ui.py resolves ui.py relative to itself,
' so this only has to be right enough to find launch_ui.py.
here = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = here
target = here & "\launch_ui.py"

If Not fso.FileExists(target) Then
  MsgBox "launch_ui.py is not next to this file." & vbCrLf & vbCrLf & _
         "Looked in:" & vbCrLf & here & vbCrLf & vbCrLf & _
         "Keep Dashboard.vbs in the repository folder.", _
         16, "Asteroid Pipeline"
  WScript.Quit 1
End If

' `pyw` is the Windows launcher's windowless interpreter and the one this repo
' documents. `pythonw` is the fallback, probed rather than assumed because a
' machine with no Python has a Microsoft Store ALIAS of that name which exists,
' runs, and fails -- the same trap run.bat documents for a bare `python`.
py = ""
If Probe("pyw -3") Then
  py = "pyw -3"
ElseIf Probe("pythonw") Then
  py = "pythonw"
End If

If py = "" Then
  MsgBox "Python was not found." & vbCrLf & vbCrLf & _
         "Install Python 3.11 or newer from python.org and tick" & vbCrLf & _
         """Add python.exe to PATH"" in the installer, then" & vbCrLf & _
         "double-click this file again.", _
         16, "Asteroid Pipeline"
  WScript.Quit 1
End If

' 0 = no window, False = do not wait. launch_ui.py puts up its own window
' within a second or so and owns everything after this point.
sh.Run py & " """ & target & """", 0, False
WScript.Quit 0


' --------------------------------------------------------------------------
Function Probe(exe)
  ' True if `exe` runs and exits 0. Window style 0 so the probe itself cannot
  ' flash a console -- which would defeat the entire point of this file.
  Dim rc
  Probe = False
  On Error Resume Next
  rc = sh.Run(exe & " -c ""import sys""", 0, True)
  If Err.Number = 0 Then Probe = (rc = 0)
  Err.Clear
  On Error GoTo 0
End Function
