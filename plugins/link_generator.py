#(©)Codexbotz - updated
import re
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait
from bot import Bot
from config import ADMINS
from helper_func import encode, get_message_id, get_album_message_ids, encode_album

# helper: try to extract last integer from a t.me link (message id)
def _extract_msg_id_from_link(link: str):
    if not link:
        return None
    if link.isdigit():
        return int(link)
    nums = re.findall(r'-?\d+', link)
    if not nums:
        return None
    try:
        return int(nums[-1])
    except:
        return None

# shared reply keyboard factory
def _share_markup(link: str):
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔁 Share URL", url=f'https://telegram.me/share/url?url={link}')]])


# ──────────────────────────────────────────────────────────────────────────────
# ALBUM COLLECTION HELPER
# Pyrogram fires one update per photo/video in an album.
# We buffer them for a short window then process together.
# ──────────────────────────────────────────────────────────────────────────────
_album_buffer: dict = {}   # media_group_id -> {"msgs": [...], "task": asyncio.Task}
_ALBUM_WAIT = 1.0          # seconds to wait for remaining album parts


async def _process_album(client: Client, media_group_id: str):
    """Called after the buffer window closes. Generates a link for the whole album."""
    await asyncio.sleep(_ALBUM_WAIT)
    data = _album_buffer.pop(media_group_id, None)
    if not data:
        return
    msgs = sorted(data["msgs"], key=lambda m: m.id)
    first_msg = msgs[0]

    try:
        # Copy entire media group to DB channel — no forward tag, album grouping preserved
        copied_msgs = await first_msg.copy_media_group(chat_id=client.db_channel.id)
        copied_msgs = sorted(copied_msgs, key=lambda m: m.id)
        fwd_ids = [m.id for m in copied_msgs]

        base64_string = await encode_album(client, fwd_ids)
        link = f"https://t.me/{client.username}?start={base64_string}"
        await first_msg.reply_text(
            f"<b>Here is your album link</b> ({len(fwd_ids)} files)\n\n{link}",
            quote=True,
            reply_markup=_share_markup(link)
        )
    except Exception as e:
        await first_msg.reply_text(f"❌ Error generating album link: `{e}`", quote=True)


# ──────────────────────────────────────────────────────────────────────────────
# HANDLER: Admin sends media directly (single file OR album)
# ──────────────────────────────────────────────────────────────────────────────
@Bot.on_message(filters.private & filters.user(ADMINS) & (
    filters.document | filters.video | filters.photo |
    filters.audio | filters.voice | filters.sticker
))
async def media_genlink(client: Client, message: Message):
    # ── Album case ──
    if message.media_group_id:
        mgid = message.media_group_id
        if mgid not in _album_buffer:
            _album_buffer[mgid] = {"msgs": [], "task": None}
        _album_buffer[mgid]["msgs"].append(message)
        # Cancel old timer, restart it
        if _album_buffer[mgid]["task"]:
            _album_buffer[mgid]["task"].cancel()
        _album_buffer[mgid]["task"] = asyncio.create_task(
            _process_album(client, mgid)
        )
        return  # wait for all parts to arrive

    # ── Single file case ──
    try:
        forwarded = await client.forward_messages(
            chat_id=client.db_channel.id,
            from_chat_id=message.chat.id,
            message_ids=message.id
        )
        fmsg = forwarded[0] if isinstance(forwarded, list) else forwarded
        msg_id = fmsg.id
        base64_string = await encode(f"get-{msg_id * abs(client.db_channel.id)}")
        link = f"https://t.me/{client.username}?start={base64_string}"
        await message.reply_text(
            f"<b>Here is your link</b>\n\n{link}",
            quote=True,
            reply_markup=_share_markup(link)
        )
    except Exception as e:
        await message.reply_text(f"❌ Error generating link: `{e}`", quote=True)


# ──────────────────────────────────────────────────────────────────────────────
# HANDLER: /genlink
# ──────────────────────────────────────────────────────────────────────────────
@Bot.on_message(filters.private & filters.user(ADMINS) & filters.command('genlink'))
async def link_generator(client: Client, message: Message):
    # ── Argument path: /genlink <t.me link or msg id> ──
    cmd_parts = message.text.split(maxsplit=1)
    if len(cmd_parts) > 1:
        arg = cmd_parts[1].strip()
        parsed_id = _extract_msg_id_from_link(arg)
        if parsed_id:
            # Fetch the message from DB channel and check for album
            link = await _genlink_from_db_msg_id(client, message, parsed_id)
            if link:
                return
        # fall through to interactive

    # ── Reply path ──
    target = message.reply_to_message
    if target:
        msg_id = await get_message_id(client, target)
        if msg_id:
            link = await _genlink_from_db_msg_id(client, message, msg_id)
            if link:
                return
        # reply contains media not yet in DB — forward it
        if target.media:
            if target.media_group_id:
                await message.reply_text(
                    "⚠️ To generate an album link, please send the album files directly to me instead of replying.",
                    quote=True
                )
                return
            try:
                fmsg = await target.copy(chat_id=client.db_channel.id)
                base64_string = await encode(f"get-{fmsg.id * abs(client.db_channel.id)}")
                link = f"https://t.me/{client.username}?start={base64_string}"
                await message.reply_text(
                    f"<b>Here is your link</b>\n\n{link}",
                    quote=True,
                    reply_markup=_share_markup(link)
                )
                return
            except Exception as e:
                await message.reply_text(f"❌ Error forwarding media to DB channel: `{e}`", quote=True)
                return

    # ── Interactive fallback ──
    while True:
        try:
            channel_message = await client.ask(
                text=(
                    "Forward a message from the DB Channel (with Quotes)..\n"
                    "or Send the DB Channel Post link\n\n"
                    "💡 If it's an album post, send its t.me link and I'll fetch the full album."
                ),
                chat_id=message.from_user.id,
                filters=(filters.forwarded | (filters.text & ~filters.forwarded)),
                timeout=60
            )
        except:
            return
        msg_id = await get_message_id(client, channel_message)
        if msg_id:
            await _genlink_from_db_msg_id(client, channel_message, msg_id, reply_target=channel_message)
            return
        else:
            await channel_message.reply(
                "❌ Error\n\nThis forwarded post is not from my DB Channel or this link is not from the DB Channel",
                quote=True
            )
            continue


async def _genlink_from_db_msg_id(client: Client, trigger_msg: Message, msg_id: int, reply_target=None):
    """
    Fetch msg_id from DB channel. If it's part of an album, collect all album IDs
    and return an album link. Otherwise return a single-file link.
    reply_target: the message to reply to (defaults to trigger_msg).
    """
    reply_to = reply_target or trigger_msg
    try:
        db_msg = await client.get_messages(
            chat_id=client.db_channel.id,
            message_ids=msg_id
        )
    except Exception as e:
        await reply_to.reply_text(f"❌ Could not fetch message from DB channel: `{e}`", quote=True)
        return None

    if db_msg and not db_msg.empty and db_msg.media_group_id:
        # It's part of an album — collect all IDs
        album_ids = await get_album_message_ids(
            client, client.db_channel.id, db_msg.media_group_id, msg_id
        )
        base64_string = await encode_album(client, album_ids)
        link = f"https://t.me/{client.username}?start={base64_string}"
        await reply_to.reply_text(
            f"<b>Here is your album link</b> ({len(album_ids)} files)\n\n{link}",
            quote=True,
            reply_markup=_share_markup(link)
        )
    else:
        # Single message
        base64_string = await encode(f"get-{msg_id * abs(client.db_channel.id)}")
        link = f"https://t.me/{client.username}?start={base64_string}"
        await reply_to.reply_text(
            f"<b>Here is your link</b>\n\n{link}",
            quote=True,
            reply_markup=_share_markup(link)
        )
    return link


# ──────────────────────────────────────────────────────────────────────────────
# HANDLER: /batch  (unchanged — range based, not album aware)
# ──────────────────────────────────────────────────────────────────────────────
@Bot.on_message(filters.private & filters.user(ADMINS) & filters.command('batch'))
async def batch(client: Client, message: Message):
    cmd_parts = message.text.split(maxsplit=2)
    if len(cmd_parts) >= 3:
        start_arg = cmd_parts[1].strip()
        end_arg = cmd_parts[2].strip()
        start_id = _extract_msg_id_from_link(start_arg)
        end_id = _extract_msg_id_from_link(end_arg)
        if start_id and end_id:
            string = f"get-{start_id * abs(client.db_channel.id)}-{end_id * abs(client.db_channel.id)}"
            base64_string = await encode(string)
            link = f"https://t.me/{client.username}?start={base64_string}"
            await message.reply_text(
                f"<b>Here is your link</b>\n\n{link}",
                quote=True,
                reply_markup=_share_markup(link)
            )
            return

    while True:
        try:
            first_message = await client.ask(
                text="Forward the First Message from DB Channel (with Quotes)..\n\nor Send the DB Channel Post Link",
                chat_id=message.from_user.id,
                filters=(filters.forwarded | (filters.text & ~filters.forwarded)),
                timeout=60
            )
        except:
            return
        f_msg_id = await get_message_id(client, first_message)
        if not f_msg_id and first_message.text:
            parsed = _extract_msg_id_from_link(first_message.text.strip())
            if parsed:
                f_msg_id = parsed
        if f_msg_id:
            break
        else:
            await first_message.reply(
                "❌ Error\n\nThis forwarded post is not from my DB Channel or this link is taken from DB Channel",
                quote=True
            )
            continue

    while True:
        try:
            second_message = await client.ask(
                text="Forward the Last Message from DB Channel (with Quotes)..\nor Send the DB Channel Post link",
                chat_id=message.from_user.id,
                filters=(filters.forwarded | (filters.text & ~filters.forwarded)),
                timeout=60
            )
        except:
            return
        s_msg_id = await get_message_id(client, second_message)
        if not s_msg_id and second_message.text:
            parsed = _extract_msg_id_from_link(second_message.text.strip())
            if parsed:
                s_msg_id = parsed
        if s_msg_id:
            break
        else:
            await second_message.reply(
                "❌ Error\n\nThis forwarded post is not from my DB Channel or this link is taken from DB Channel",
                quote=True
            )
            continue

    string = f"get-{f_msg_id * abs(client.db_channel.id)}-{s_msg_id * abs(client.db_channel.id)}"
    base64_string = await encode(string)
    link = f"https://t.me/{client.username}?start={base64_string}"
    await second_message.reply_text(
        f"<b>Here is your link</b>\n\n{link}",
        quote=True,
        reply_markup=_share_markup(link)
    )
