#(©)Codexbotz - updated
import re
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from bot import Bot
from config import ADMINS
from helper_func import encode, get_message_id

# helper: try to extract last integer from a t.me link (message id)
def _extract_msg_id_from_link(link: str):
    # common t.me link forms:
    # https://t.me/username/123
    # https://t.me/c/ - private: https://t.me/c/-1001234567/89
    # or just numeric string
    if not link:
        return None
    # if the whole argument is numeric, return it direct
    if link.isdigit():
        return int(link)
    # find all numbers and return the last one (message id usually the last)
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

# New handler: accept media sent directly to bot (private) and generate link
@Bot.on_message(filters.private & filters.user(ADMINS) & (filters.document | filters.video | filters.photo | filters.audio | filters.voice | filters.sticker))
async def media_genlink(client: Client, message: Message):
    """
    If admin sends any media directly, forward it to DB channel, get the new message id,
    build the encoded start parameter and reply with the link.
    """
    try:
        # forward the single media message to db_channel to keep DB consistent
        forwarded = await client.forward_messages(
            chat_id=client.db_channel.id,
            from_chat_id=message.chat.id,
            message_ids=message.message_id
        )
        # forwarded can be a Message or list -- handle both
        if isinstance(forwarded, list):
            fmsg = forwarded[0]
        else:
            fmsg = forwarded

        msg_id = fmsg.message_id
        base64_string = await encode(f"get-{msg_id * abs(client.db_channel.id)}")
        link = f"https://t.me/{client.username}?start={base64_string}"
        await message.reply_text(f"<b>Here is your link</b>\n\n{link}", quote=True, reply_markup=_share_markup(link))
    except Exception as e:
        await message.reply_text(f"❌ Error generating link: `{e}`", quote=True)


@Bot.on_message(filters.private & filters.user(ADMINS) & filters.command('genlink'))
async def link_generator(client: Client, message: Message):
    """
    /genlink
    /genlink <t.me/link_or_msgid>
    Also works if the admin replies/forwards a message (or forwarded message from DB channel).
    """
    # If the command has an argument, try to parse it as a link/msg id
    cmd_parts = message.text.split(maxsplit=1)
    if len(cmd_parts) > 1:
        arg = cmd_parts[1].strip()
        # try parse integer msg id from link
        parsed_id = _extract_msg_id_from_link(arg)
        if parsed_id:
            # if it's a message id from the DB channel, we can try use get_message_id (if needed),
            # but following original behavior: compute encoded token using msg_id * abs(db_channel.id)
            base64_string = await encode(f"get-{parsed_id * abs(client.db_channel.id)}")
            link = f"https://t.me/{client.username}?start={base64_string}"
            await message.reply_text(f"<b>Here is your link</b>\n\n{link}", quote=True, reply_markup=_share_markup(link))
            return
        # if not parseable, fall through to interactive / reply handling

    # If user replied to a message (or forwarded one), try to extract msg id using get_message_id
    target = message.reply_to_message
    if target:
        msg_id = await get_message_id(client, target)
        if msg_id:
            base64_string = await encode(f"get-{msg_id * abs(client.db_channel.id)}")
            link = f"https://t.me/{client.username}?start={base64_string}"
            await message.reply_text(f"<b>Here is your link</b>\n\n{link}", quote=True, reply_markup=_share_markup(link))
            return
        # if get_message_id failed and the reply contains media, forward it to DB channel and generate
        if target.media:
            try:
                forwarded = await client.forward_messages(
                    chat_id=client.db_channel.id,
                    from_chat_id=target.chat.id,
                    message_ids=target.message_id
                )
                fmsg = forwarded[0] if isinstance(forwarded, list) else forwarded
                msg_id = fmsg.message_id
                base64_string = await encode(f"get-{msg_id * abs(client.db_channel.id)}")
                link = f"https://t.me/{client.username}?start={base64_string}"
                await message.reply_text(f"<b>Here is your link</b>\n\n{link}", quote=True, reply_markup=_share_markup(link))
                return
            except Exception as e:
                await message.reply_text(f"❌ Error forwarding media to DB channel: `{e}`", quote=True)
                return

    # fallback: interactive ask (existing behavior)
    while True:
        try:
            channel_message = await client.ask(
                text="Forward Message from the DB Channel (with Quotes)..\nor Send the DB Channel Post link",
                chat_id=message.from_user.id,
                filters=(filters.forwarded | (filters.text & ~filters.forwarded)),
                timeout=60
            )
        except:
            return
        msg_id = await get_message_id(client, channel_message)
        if msg_id:
            base64_string = await encode(f"get-{msg_id * abs(client.db_channel.id)}")
            link = f"https://t.me/{client.username}?start={base64_string}"
            reply_markup = _share_markup(link)
            await channel_message.reply_text(f"<b>Here is your link</b>\n\n{link}", quote=True, reply_markup=reply_markup)
            return
        else:
            await channel_message.reply("❌ Error\n\nthis Forwarded Post is not from my DB Channel or this Link is not taken from DB Channel", quote=True)
            continue


@Bot.on_message(filters.private & filters.user(ADMINS) & filters.command('batch'))
async def batch(client: Client, message: Message):
    """
    /batch                 -> interactive (existing ask flow)
    /batch <start> <end>   -> parse message links or numeric ids and generate link
    """
    # Try the quick-args path first
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
            reply_markup = _share_markup(link)
            await message.reply_text(f"<b>Here is your link</b>\n\n{link}", quote=True, reply_markup=reply_markup)
            return
        # if parsing failed, fall back to interactive below

    # Interactive: ask for first and second message (existing behavior)
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
        # if user provided a direct link instead of forwarding, try to parse numeric id from text
        if not f_msg_id and first_message.text:
            parsed = _extract_msg_id_from_link(first_message.text.strip())
            if parsed:
                f_msg_id = parsed
        if f_msg_id:
            break
        else:
            await first_message.reply("❌ Error\n\nthis Forwarded Post is not from my DB Channel or this Link is taken from DB Channel", quote=True)
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
            await second_message.reply("❌ Error\n\nthis Forwarded Post is not from my DB Channel or this Link is taken from DB Channel", quote=True)
            continue

    string = f"get-{f_msg_id * abs(client.db_channel.id)}-{s_msg_id * abs(client.db_channel.id)}"
    base64_string = await encode(string)
    link = f"https://t.me/{client.username}?start={base64_string}"
    reply_markup = _share_markup(link)
    await second_message.reply_text(f"<b>Here is your link</b>\n\n{link}", quote=True, reply_markup=reply_markup)