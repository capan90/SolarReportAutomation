' SolarReportAutomation - Dashboard web sunucusu gizli (windowless) baslatici
' Neden: Task Scheduler python.exe'yi interaktif oturumda calistirinca masaustunde
' konsol penceresi beliriyordu (PlantStatus ile ayni sorun). Bu VBS sunucuyu gizli
' pencere (0) ile baslatir ve bitmesini BEKLER (True).
' Yeniden baslatma dongusu BURADADIR: Task Scheduler'in "restart on failure" ayari
' yalnizca gorev BASLATILAMAZSA devreye girer; calisan programin sifir olmayan exit
' koduyla bitmesini failure saymaz (2026-07-21'de deneyle dogrulandi). Bu yuzden:
'   - rc = 10 (RESTART_EXIT_CODE, kontrollu restart / ayar degisikligi)
'     -> hemen yeniden baslat (kesinti birkac saniye)
'   - rc <> 0 (cokme) -> 1 dk bekle, art arda en fazla 3 deneme
'   - rc = 0  (temiz kapanis) -> donguden cik
' Proje koku script konumundan turetilir (dev laptop ve prod APPS sunucusunda ayni
' dosya calisir, sabit yol yok). CurrentDirectory atamasi sart: Task Scheduler
' cwd'si System32 olabilir (WinError 5).
Set fso = CreateObject("Scripting.FileSystemObject")
projRoot = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = projRoot
cmd = """" & projRoot & "\.venv\Scripts\python.exe"" -m app.dashboard.web_server"

' Dongu pes ettiginde (art arda 4 cokme) sistem yoneticisine e-posta uyarisi
' gonderilir — aksi halde dashboard'in kapali kaldigi ancak biri fark edince
' anlasiliyor (2026-07-21 olayi). Best-effort: uyari da basarisiz olsa yutulur.
alertCmd = """" & projRoot & "\.venv\Scripts\python.exe"" """ & projRoot & "\scripts\send_dashboard_down_alert.py"""

attempts = 0
Do
    rc = sh.Run(cmd, 0, True)
    If rc = 10 Then
        attempts = 0
    ElseIf rc <> 0 Then
        attempts = attempts + 1
        If attempts > 3 Then
            On Error Resume Next
            sh.Run alertCmd, 0, True
            On Error GoTo 0
            Exit Do
        End If
        WScript.Sleep 60000
    End If
Loop While rc <> 0
WScript.Quit rc
