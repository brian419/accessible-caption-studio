# Platform setup

Accessible Caption Studio keeps projects and model caches local. Python 3 is only needed for the first bootstrap; the launchers then create a project-local Python 3.11 runtime and environment.

## macOS

Double-click `Start Accessible Caption Studio.command`, or run it from Terminal. The existing macOS launcher remains the primary path on Intel Macs.

## Linux

Install FFmpeg with your distribution package manager, then run:

```bash
chmod +x start-accessible-caption-studio.sh
./start-accessible-caption-studio.sh
```

## Windows

Install FFmpeg and make `ffmpeg` and `ffprobe` available on PATH. From PowerShell in the repository folder run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\Start Accessible Caption Studio.ps1
```

The Settings > System readiness section confirms FFmpeg, FFprobe, Python, disk space, and recovered jobs before long processing work.
