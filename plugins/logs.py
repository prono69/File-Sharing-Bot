import os
from pyrogram import Client, filters
from pyrogram.types import Message
from bot import Bot
from config import ADMINS

LOG_FILE = "filesharingbot.txt"


@Bot.on_message(filters.private & filters.user(ADMINS) & filters.command("logs"))
async def log_cmd(client: Client, message: Message):

    # If file doesn't exist, create it empty
    if not os.path.exists(LOG_FILE):
        open(LOG_FILE, "w").close()

    # If command is "/log o" → read & send the last 100 lines
    if len(message.command) > 1 and message.command[1].lower() == "o":
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            # Get last 100 lines or all lines if fewer than 100
            last_100_lines = lines[-100:] if len(lines) > 100 else lines
            content = "".join(last_100_lines) or "Log file is empty."
            
            await message.reply_text(
                f"<b>📖 Last 100 Lines from Log File</b>\n\n<code>{content}</code>",
                quote=True
            )
        except Exception as e:
            await message.reply_text(f"❌ Error reading log file:\n`{e}`")
        return

    # /log → send file as document
    try:
        await message.reply_document(
            document=LOG_FILE,
            caption="📁 <b>filesharingbot.txt</b>",
            quote=True
        )
    except Exception as e:
        await message.reply_text(f"❌ Error sending log file:\n`{e}`")