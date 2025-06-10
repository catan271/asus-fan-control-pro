# Asus Fan Controller PRO

Thought MyASUS provide me with fan profile options. But they don't seem to be very effective. I encounter overheating a lot, especially when the CPU go under heavy load, and the temperature is about 50-60°C, the fan doesn't run fast enough - in my opinion - to prevent the heat from heating up the upper surface of the laptop. That would be very annoying if you are playing games with keyboard, and wouldn't be good for the hardwares in the long run.

One day I came across some repos on Github that provide applications to control the fan of Asus Vivobook laptops. But those applications don't work if your machine is using ASUS System Control Interface driver v3.1.39.0 or later. I guess that the APIs that were used to control the fans now require SYSTEM privilege to run. So I came up with the solution of leveraging PsExec and nssm. After hours of working on the project, I finally made it work. The app can be setup to run as a System service on Windows startup, so you don't have to open it up every time.

# Prerequisites

- Your Laptop must be ASUS (obviously) and have the Fan testing feature in MyASUS app.
- Python 3.10 (I recommend you create a separated environment using `conda`. Believe me, `conda` is the best)
- Find `AsusWinIO64.dll` in `C:\Windows\System32` and put it in the root directory.
- You should run the IDE in Administrator mode.

# Build

```
.\build.bat
```

# Develop

Create `dev.bat` similar to `run.bat`, but change the command from `"%~dp0main.exe"` to `path/to/python "%~dp0main.py"`

```
.\dev.bat
```
