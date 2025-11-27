import asyncio
from io import BytesIO
from pyrogram import Client, filters
from pyrogram.types import Message
from bot import Bot
from config import ADMINS

MAX_MESSAGE_LENGTH = 4096

@Bot.on_message(filters.command("bash") & filters.user(ADMINS))
async def execution(client: Client, message: Message):
    status_message = await message.reply_text("`Processing ...`")

    try:
        cmd = message.text.split(" ", maxsplit=1)[1]
    except IndexError:
        return await status_message.edit("No command provided!")

    reply_to_ = message.reply_to_message or message

    process = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()

    stderr_output = stderr.decode().strip() or "😂"
    stdout_output = stdout.decode().strip() or "😐"

    output = (
        f"<b>QUERY:</b>\n<u>Command:</u>\n<code>{cmd}</code>\n"
        f"<u>PID</u>: <code>{process.pid}</code>\n\n"
        f"<b>stderr</b>: \n<code>{stderr_output}</code>\n\n"
        f"<b>stdout</b>: \n<code>{stdout_output}</code>"
    )

    if len(output) > MAX_MESSAGE_LENGTH:
        with BytesIO(output.encode()) as out_file:
            out_file.name = "exec.txt"
            await reply_to_.reply_document(
                document=out_file,
                caption=cmd[: MAX_MESSAGE_LENGTH // 4 - 1],
                disable_notification=True,
                quote=True,
            )
    else:
        await reply_to_.reply_text(output, quote=True)

    await status_message.delete()