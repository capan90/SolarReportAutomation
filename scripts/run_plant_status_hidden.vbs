' SolarReportAutomation - PlantStatusJob gizli (windowless) baslatici
' Neden: Task Scheduler python.exe'yi interaktif oturumda calistirinca masaustunde
' bir konsol penceresi beliriyordu. Bu VBS ayni komutu gizli pencere (0) ile calistirir;
' python.exe konsola sahip oldugundan print() cikti sorunu yasanmaz (pythonw riski yok).
' Job zaten headless=True tarayici kullaniyor; login/CAPTCHA akisi etkilenmez.
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Users\Murat Capan\Desktop\SolarReportAutomation"
sh.Run """C:\Users\Murat Capan\Desktop\SolarReportAutomation\.venv\Scripts\python.exe"" ""C:\Users\Murat Capan\Desktop\SolarReportAutomation\main.py"" --plant-status", 0, False
