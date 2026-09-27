"""
Discord selfbot: when someone sends you an Instagram or TikTok link in a DM or group chat,
reply with the same link rewritten to oginstagram / tfxktok. When you send one yourself,
your message is edited in place instead. Both go out through one queue with a fixed delay
between each one.
"""

import asyncio
import logging
import os
import re
from pathlib import Path

import discord

DELAY_SECONDS = 30
INSTAGRAM_REPLACEMENT = "oginstagram.com"
TIKTOK_REPLACEMENT = "tfxktok.com"

# Matches instagram.com and tiktok.com links (with or without www./m./vm. etc). Stops at
# whitespace and characters Discord uses for markdown/embeds suppression like <>, (), and ||.
SOCIAL_URL = re.compile(r"(https?://)((?:[\w-]+\.)*)(instagram|tiktok)\.com(/[^\s<>()|]+)", re.IGNORECASE)

log = logging.getLogger("insta-selfbot")


def load_token() -> str:
    token = os.environ.get("DISCORD_TOKEN")
    env_file = Path(__file__).with_name(".env")
    if not token and env_file.exists():
        for line in env_file.read_text().splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "DISCORD_TOKEN":
                token = value.strip().strip('"').strip("'")
    if not token:
        raise SystemExit("No token found. Put DISCORD_TOKEN=your_token in .env next to bot.py.")
    return token


def convert_url(match: re.Match) -> str:
    scheme, subdomains, site, path = match.groups()
    # www. is the only subdomain kept: www.tiktok.com -> www.tfxktok.com, pro.tiktok.com -> tfxktok.com
    prefix = subdomains if subdomains.lower() == "www." else ""
    domain = TIKTOK_REPLACEMENT if site.lower() == "tiktok" else INSTAGRAM_REPLACEMENT
    return f"{scheme}{prefix}{domain}{path}"


def convert_links(text: str) -> list[str]:
    converted = []
    for match in SOCIAL_URL.finditer(text):
        url = convert_url(match)
        if url not in converted:
            converted.append(url)
    return converted


def rewrite_links(text: str) -> str:
    return SOCIAL_URL.sub(convert_url, text)


class InstaSelfbot(discord.Client):
    def __init__(self):
        super().__init__()
        # (message, is_own). Your own messages get edited in place, everyone else's get a reply.
        self.queue: asyncio.Queue[tuple[discord.Message, bool]] = asyncio.Queue()
        # IDs of messages still waiting in the queue. Deleting one removes it from here so the
        # worker skips it instead of replying to (or editing) a message that's gone.
        self.pending: set[int] = set()

    async def setup_hook(self):
        self.loop.create_task(self.reply_worker())

    async def on_ready(self):
        log.info("Logged in as %s (%s)", self.user, self.user.id)

    async def on_message(self, message: discord.Message):
        if not isinstance(message.channel, (discord.DMChannel, discord.GroupChannel)):
            return
        # Converted links (oginstagram.com, tfxktok.com) don't match, so the bot's own replies
        # and already-edited messages are ignored here.
        if not SOCIAL_URL.search(message.content):
            return

        own = message.author.id == self.user.id
        self.pending.add(message.id)
        await self.queue.put((message, own))
        log.info("Queued %s from %s (queue size: %d)", "edit" if own else "link", message.author, self.queue.qsize())

    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        # Raw event so it fires even if the message has dropped out of discord.py's cache.
        self.pending.discard(payload.message_id)

    async def reply_worker(self):
        while True:
            message, own = await self.queue.get()
            if message.id not in self.pending:
                # Deleted while waiting. Nothing is sent, so skip the delay.
                log.info("Skipped %s, deleted while queued (%d left in queue)", message.jump_url, self.queue.qsize())
                continue
            self.pending.discard(message.id)
            # Content is read now rather than at queue time: discord.py updates cached messages
            # in place, so an edit made while waiting in the queue isn't overwritten or missed.
            try:
                if own:
                    new_content = rewrite_links(message.content)
                    if new_content == message.content:
                        continue
                    await message.edit(content=new_content)
                else:
                    links = convert_links(message.content)
                    if not links:
                        continue
                    await message.reply("\n".join(links))
            except discord.HTTPException as e:
                # Message deleted, no permission, too long after rewriting, etc. Nothing was
                # sent, so skip the delay.
                log.warning("Couldn't %s %s: %s", "edit" if own else "reply to", message.jump_url, e)
                continue
            log.info("%s %s (%d left in queue)", "Edited" if own else "Replied to", message.jump_url, self.queue.qsize())
            await asyncio.sleep(DELAY_SECONDS)


if __name__ == "__main__":
    InstaSelfbot().run(load_token(), log_level=logging.INFO, root_logger=True)
