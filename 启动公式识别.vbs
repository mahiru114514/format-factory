Option Explicit
Dim fs, shell, base, exe, python, command
Set fs = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
base = fs.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = base
exe = fs.BuildPath(base, "deliverables\desktop-input-fix-v0.1.5\FormatFactory\FormatFactory.exe")
If Not fs.FileExists(exe) Then exe = fs.BuildPath(base, "deliverables\desktop-office-copy-v0.1.4\FormatFactory\FormatFactory.exe")
python = fs.BuildPath(base, ".venv\Scripts\pythonw.exe")
If fs.FileExists(exe) Then
    command = Chr(34) & exe & Chr(34) & " --formula-workspace"
ElseIf fs.FileExists(python) Then
    command = Chr(34) & python & Chr(34) & " -X utf8 " & Chr(34) & fs.BuildPath(base, "main.py") & Chr(34) & " --formula-workspace"
Else
    MsgBox "Formula workspace runtime not found.", 48, "Format Factory"
    WScript.Quit 1
End If
shell.Run command, 1, False
