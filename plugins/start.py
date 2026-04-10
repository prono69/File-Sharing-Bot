#(©)CodeXBotz

import os
import asyncio
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, InputMediaVideo, InputMediaDocument, InputMediaAudio
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated

from bot import Bot
from config import ADMINS, FORCE_MSG, START_MSG, CUSTOM_CAPTION, DISABLE_CHANNEL_BUTTON, PROTECT_CONTENT, START_PIC, AUTO_DELETE_TIME, AUTO_DELETE_MSG, JOIN_REQUEST_ENABLE, FORCE_SUB_CHANNEL
from helper_func import subscribed, decode, get_messages, delete_file
from database.database import add_user, del_user, full_userbase, present_user

LOG_CHANNEL = -1001684936508


def _build_input_media(msg, caption=None):
    """Convert a pyrogram Message into an InputMedia* object for send_media_group."""
    cap = caption if caption is not None else (msg.caption.html if msg.caption else "")
    if msg.photo:
        return InputMediaPhoto(media=msg.photo.file_id, caption=cap, parse_mode=ParseMode.HTML)
    elif msg.video:
        return InputMediaVideo(media=msg.video.file_id, caption=cap, parse_mode=ParseMode.HTML)
    elif msg.document:
        return InputMediaDocument(media=msg.document.file_id, caption=cap, parse_mode=ParseMode.HTML)
    elif msg.audio:
        return InputMediaAudio(media=msg.audio.file_id, caption=cap, parse_mode=ParseMode.HTML)
    return None


async def _send_album(client: Client, chat_id: int, messages: list, protect_content: bool = False):
    """
    Send a list of DB-channel messages as a media group (album) to chat_id.
    Returns the list of sent messages (for tracking deletion).
    """
    media_list = []
    for i, msg in enumerate(messages):
        if CUSTOM_CAPTION and msg.document:
            cap = CUSTOM_CAPTION.format(
                previouscaption="" if not msg.caption else msg.caption.html,
                filename=msg.document.file_name
            )
        else:
            cap = msg.caption.html if msg.caption else ""
        # Only first item in a media group carries the caption visually
        item_cap = cap if i == 0 else ""
        media_item = _build_input_media(msg, caption=item_cap)
        if media_item:
            media_list.append(media_item)

    if not media_list:
        return []

    try:
        sent = await client.send_media_group(
            chat_id=chat_id,
            media=media_list,
            protect_content=protect_content
        )
    except FloodWait as e:
        await asyncio.sleep(e.value)
        sent = await client.send_media_group(
            chat_id=chat_id,
            media=media_list,
            protect_content=protect_content
        )
    return sent if isinstance(sent, list) else [sent]


@Bot.on_message(filters.command('start') & filters.private & subscribed)
async def start_command(client: Client, message: Message):
    id = message.from_user.id

    is_new_user = False
    if not await present_user(id):
        try:
            await add_user(id)
            is_new_user = True
        except:
            pass

    # 🔔 Log new users
    if is_new_user:
        try:
            username = (
                f"@{message.from_user.username}"
                if message.from_user.username
                else "<i>Not set</i>"
            )
            log_text = (
                "🆕 <b>A new user detected!</b>\n\n"
                f"👤 <b>Name:</b> {message.from_user.mention}\n"
                f"🔗 <b>Username:</b> {username}\n"
                f"🆔 <b>User ID:</b> <code>{message.from_user.id}</code>"
            )
            await client.send_message(
                chat_id=LOG_CHANNEL,
                text=log_text,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            try:
                client.LOGGER(__name__).warning(f"Failed to send new-user log: {e}")
            except:
                pass

    text = message.text
    if len(text) > 7:
        try:
            base64_string = text.split(" ", 1)[1]
        except:
            return

        string = await decode(base64_string)
        argument = string.split("-")

        # ── ALBUM link: "get-album-ID1_ID2_ID3" ──
        if len(argument) >= 3 and argument[1] == "album":
            try:
                raw_ids = argument[2].split("_")
                ids = [int(int(x) / abs(client.db_channel.id)) for x in raw_ids]
            except:
                return

            temp_msg = await message.reply("Please wait...")
            try:
                messages_list = await get_messages(client, ids)
            except:
                await message.reply_text("Something went wrong..!")
                return
            await temp_msg.delete()

            track_msgs = []

            if AUTO_DELETE_TIME and AUTO_DELETE_TIME > 0:
                sent = await _send_album(client, message.from_user.id, messages_list, protect_content=PROTECT_CONTENT)
                track_msgs.extend(sent)
            else:
                await _send_album(client, message.from_user.id, messages_list, protect_content=PROTECT_CONTENT)

            if track_msgs:
                delete_data = await client.send_message(
                    chat_id=message.from_user.id,
                    text=AUTO_DELETE_MSG
                )
                asyncio.create_task(delete_file(track_msgs, client, delete_data))

            return

        # ── BATCH link: "get-START-END" ──
        if len(argument) == 3:
            try:
                start = int(int(argument[1]) / abs(client.db_channel.id))
                end = int(int(argument[2]) / abs(client.db_channel.id))
            except:
                return
            if start <= end:
                ids = range(start, end + 1)
            else:
                ids = []
                i = start
                while True:
                    ids.append(i)
                    i -= 1
                    if i < end:
                        break

        # ── SINGLE link: "get-ID" ──
        elif len(argument) == 2:
            try:
                ids = [int(int(argument[1]) / abs(client.db_channel.id))]
            except:
                return

        temp_msg = await message.reply("Please wait...")
        try:
            messages_list = await get_messages(client, ids)
        except:
            await message.reply_text("Something went wrong..!")
            return
        await temp_msg.delete()

        track_msgs = []

        for msg in messages_list:
            if bool(CUSTOM_CAPTION) & bool(msg.document):
                caption = CUSTOM_CAPTION.format(
                    previouscaption="" if not msg.caption else msg.caption.html,
                    filename=msg.document.file_name
                )
            else:
                caption = "" if not msg.caption else msg.caption.html

            if DISABLE_CHANNEL_BUTTON:
                reply_markup = msg.reply_markup
            else:
                reply_markup = None

            if AUTO_DELETE_TIME and AUTO_DELETE_TIME > 0:
                try:
                    copied_msg = await msg.copy(
                        chat_id=message.from_user.id,
                        caption=caption,
                        parse_mode=ParseMode.HTML,
                        reply_markup=reply_markup,
                        protect_content=PROTECT_CONTENT
                    )
                    if copied_msg:
                        track_msgs.append(copied_msg)
                except FloodWait as e:
                    await asyncio.sleep(e.value)
                    copied_msg = await msg.copy(
                        chat_id=message.from_user.id,
                        caption=caption,
                        parse_mode=ParseMode.HTML,
                        reply_markup=reply_markup,
                        protect_content=PROTECT_CONTENT
                    )
                    if copied_msg:
                        track_msgs.append(copied_msg)
                except Exception as e:
                    print(f"Error copying message: {e}")
            else:
                try:
                    await msg.copy(
                        chat_id=message.from_user.id,
                        caption=caption,
                        parse_mode=ParseMode.HTML,
                        reply_markup=reply_markup,
                        protect_content=PROTECT_CONTENT
                    )
                    await asyncio.sleep(0.5)
                except FloodWait as e:
                    await asyncio.sleep(e.value)
                    await msg.copy(
                        chat_id=message.from_user.id,
                        caption=caption,
                        parse_mode=ParseMode.HTML,
                        reply_markup=reply_markup,
                        protect_content=PROTECT_CONTENT
                    )
                except:
                    pass

        if track_msgs:
            delete_data = await client.send_message(
                chat_id=message.from_user.id,
                text=AUTO_DELETE_MSG
            )
            asyncio.create_task(delete_file(track_msgs, client, delete_data))

        return

    # ── No payload: show start message ──
    else:
        reply_markup = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("😊 About Me", callback_data="about"),
                    InlineKeyboardButton("🔒 Close", callback_data="close")
                ]
            ]
        )
        if START_PIC:
            await message.reply_photo(
                photo=START_PIC,
                caption=START_MSG.format(
                    first=message.from_user.first_name,
                    last=message.from_user.last_name,
                    username=None if not message.from_user.username else '@' + message.from_user.username,
                    mention=message.from_user.mention,
                    id=message.from_user.id
                ),
                reply_markup=reply_markup,
                quote=True
            )
        else:
            await message.reply_text(
                text=START_MSG.format(
                    first=message.from_user.first_name,
                    last=message.from_user.last_name,
                    username=None if not message.from_user.username else '@' + message.from_user.username,
                    mention=message.from_user.mention,
                    id=message.from_user.id
                ),
                reply_markup=reply_markup,
                disable_web_page_preview=True,
                quote=True
            )
        return


#=====================================================================================##

WAIT_MSG = """"<b>Processing ...</b>"""
REPLY_ERROR = """<code>Use this command as a replay to any telegram message with out any spaces.</code>"""

#=====================================================================================##


@Bot.on_message(filters.command('start') & filters.private)
async def not_joined(client: Client, message: Message):
    if bool(JOIN_REQUEST_ENABLE):
        invite = await client.create_chat_invite_link(
            chat_id=FORCE_SUB_CHANNEL,
            creates_join_request=True
        )
        ButtonUrl = invite.invite_link
    else:
        ButtonUrl = client.invitelink

    buttons = [
        [
            InlineKeyboardButton("Join Channel", url=ButtonUrl)
        ]
    ]

    try:
        buttons.append(
            [
                InlineKeyboardButton(
                    text='Try Again',
                    url=f"https://t.me/{client.username}?start={message.command[1]}"
                )
            ]
        )
    except IndexError:
        pass

    await message.reply(
        text=FORCE_MSG.format(
            first=message.from_user.first_name,
            last=message.from_user.last_name,
            username=None if not message.from_user.username else '@' + message.from_user.username,
            mention=message.from_user.mention,
            id=message.from_user.id
        ),
        reply_markup=InlineKeyboardMarkup(buttons),
        quote=True,
        disable_web_page_preview=True
    )


@Bot.on_message(filters.command('users') & filters.private & filters.user(ADMINS))
async def get_users(client: Bot, message: Message):
    msg = await client.send_message(chat_id=message.chat.id, text=WAIT_MSG)
    users = await full_userbase()
    await msg.edit(f"{len(users)} users are using this bot")


@Bot.on_message(filters.private & filters.command('broadcast') & filters.user(ADMINS))
async def send_text(client: Bot, message: Message):
    if message.reply_to_message:
        query = await full_userbase()
        broadcast_msg = message.reply_to_message
        total = 0
        successful = 0
        blocked = 0
        deleted = 0
        unsuccessful = 0

        pls_wait = await message.reply("<i>Broadcasting Message.. This will Take Some Time</i>")
        for chat_id in query:
            try:
                await broadcast_msg.copy(chat_id)
                successful += 1
            except FloodWait as e:
                await asyncio.sleep(e.x)
                await broadcast_msg.copy(chat_id)
                successful += 1
            except UserIsBlocked:
                await del_user(chat_id)
                blocked += 1
            except InputUserDeactivated:
                await del_user(chat_id)
                deleted += 1
            except:
                unsuccessful += 1
                pass
            total += 1

        status = f"""<b><u>Broadcast Completed</u>

Total Users: <code>{total}</code>
Successful: <code>{successful}</code>
Blocked Users: <code>{blocked}</code>
Deleted Accounts: <code>{deleted}</code>
Unsuccessful: <code>{unsuccessful}</code></b>"""

        return await pls_wait.edit(status)
    else:
        msg = await message.reply(REPLY_ERROR)
        await asyncio.sleep(8)
        await msg.delete()
