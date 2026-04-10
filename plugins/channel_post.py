#(©)Codexbotz

import asyncio
from pyrogram import filters, Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

from bot import Bot
from config import ADMINS, CHANNEL_ID, DISABLE_CHANNEL_BUTTON
from helper_func import encode, encode_album

# ──────────────────────────────────────────────────────────────────────────────
# Album buffer — same pattern as link_generator.py
# ──────────────────────────────────────────────────────────────────────────────
_album_buffer: dict = {}  # media_group_id -> {"msgs": [...], "task": asyncio.Task}
_ALBUM_WAIT = 1.0         # seconds to wait for all album parts to arrive

def _share_markup(link: str):
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔁 Share URL", url=f'https://telegram.me/share/url?url={link}')]])


async def _process_album(client: Client, media_group_id: str):
    """Wait for all album parts, then forward them to DB channel and generate one link."""
    await asyncio.sleep(_ALBUM_WAIT)
    data = _album_buffer.pop(media_group_id, None)
    if not data:
        return

    msgs = sorted(data["msgs"], key=lambda m: m.id)
    first_msg = msgs[0]

    reply_text = await first_msg.reply_text("Please Wait...!", quote=True)
    try:
        # Copy entire media group to DB channel — no forward tag, album grouping preserved
        copied_msgs = await first_msg.copy_media_group(
            chat_id=client.db_channel.id,
            disable_notification=True
        )
        copied_msgs = sorted(copied_msgs, key=lambda m: m.id)
        fwd_ids = [m.id for m in copied_msgs]

        base64_string = await encode_album(client, fwd_ids)
        link = f"https://t.me/{client.username}?start={base64_string}"
        markup = _share_markup(link)

        await reply_text.edit(
            f"<b>Here is your album link</b> ({len(fwd_ids)} files)\n\n{link}",
            reply_markup=markup,
            disable_web_page_preview=True
        )

    except Exception as e:
        await reply_text.edit_text(f"Something went Wrong..! `{e}`")


# ──────────────────────────────────────────────────────────────────────────────
# HANDLER: Admin sends any message/media to bot (private)
# ──────────────────────────────────────────────────────────────────────────────
@Bot.on_message(filters.private & filters.user(ADMINS) & ~filters.command(['start','users','broadcast','batch','genlink','stats', 'logs', 'bash']))
async def channel_post(client: Client, message: Message):

    # ── Album case: buffer and wait for all parts ──
    if message.media_group_id:
        mgid = message.media_group_id
        if mgid not in _album_buffer:
            _album_buffer[mgid] = {"msgs": [], "task": None}
        _album_buffer[mgid]["msgs"].append(message)
        # Reset the timer each time a new part arrives
        if _album_buffer[mgid]["task"]:
            _album_buffer[mgid]["task"].cancel()
        _album_buffer[mgid]["task"] = asyncio.create_task(
            _process_album(client, mgid)
        )
        return  # wait for remaining parts

    # ── Single message case (original behavior) ──
    reply_text = await message.reply_text("Please Wait...!", quote=True)
    try:
        post_message = await message.copy(chat_id=client.db_channel.id, disable_notification=True)
    except FloodWait as e:
        await asyncio.sleep(e.value)
        post_message = await message.copy(chat_id=client.db_channel.id, disable_notification=True)
    except Exception as e:
        print(e)
        await reply_text.edit_text("Something went Wrong..!")
        return

    converted_id = post_message.id * abs(client.db_channel.id)
    string = f"get-{converted_id}"
    base64_string = await encode(string)
    link = f"https://t.me/{client.username}?start={base64_string}"
    markup = _share_markup(link)

    await reply_text.edit(
        f"<b>Here is your link</b>\n\n{link}",
        reply_markup=markup,
        disable_web_page_preview=True
    )

    if not DISABLE_CHANNEL_BUTTON:
        try:
            await post_message.edit_reply_markup(markup)
        except FloodWait as e:
            await asyncio.sleep(e.value)
            await post_message.edit_reply_markup(markup)
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────────────────
# HANDLER: New post in the linked channel (auto-button)
# ──────────────────────────────────────────────────────────────────────────────
@Bot.on_message(filters.channel & filters.incoming & filters.chat(CHANNEL_ID))
async def new_post(client: Client, message: Message):
    if DISABLE_CHANNEL_BUTTON:
        return

    # Albums in a channel: each part gets its own button pointing to the same single-file link.
    # For a proper album link the admin should use /genlink or send directly to bot.
    converted_id = message.id * abs(client.db_channel.id)
    string = f"get-{converted_id}"
    base64_string = await encode(string)
    link = f"https://t.me/{client.username}?start={base64_string}"
    markup = _share_markup(link)
    try:
        await message.edit_reply_markup(markup)
    except FloodWait as e:
        await asyncio.sleep(e.value)
        await message.edit_reply_markup(markup)
    except Exception:
        pass
