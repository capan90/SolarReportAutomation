' SolarReportAutomation - Dashboard web sunucusu gizli (windowless) baslatici
' Neden: Task Scheduler python.exe'yi interaktif oturumda calistirinca masaustunde
' konsol penceresi beliriyordu (PlantStatus ile ayni sorun). Bu VBS sunucuyu gizli
' pencere (0) ile baslatir ve bitmesini BEKLER (True): sunucu cokerse exit kodu
' gorev sonucuna yansir ve Task Scheduler'in "restart on failure" ayari devreye girer.
' Proje koku script konumundan turetilir (dev laptop ve prod APPS sunucusunda ayni
' dosya calisir, sabit yol yok). CurrentDirectory atamasi sart: Task Scheduler
' cwd'si System32 olabilir (WinError 5).
Set fso = CreateObject("Scripting.FileSystemObject")
projRoot = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = projRoot
rc = sh.Run("""" & projRoot & "\.venv\Scripts\python.exe"" -m app.dashboard.web_server", 0, True)
WScript.Quit rc
