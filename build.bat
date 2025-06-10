pyinstaller ^
    --onedir ^
    --add-binary="%~dp0AsusWinIO64.dll:." ^
    --add-binary="%~dp0nssm.exe:." ^
    main.py -y

copy "%~dp0PsExec.exe" "%~dp0dist\main"
copy "%~dp0run.bat" "%~dp0dist\main"