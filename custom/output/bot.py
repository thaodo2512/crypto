"""Telegram bot runner — connects command handlers to python-telegram-bot.

See docs/sub-specs/SS-18.md §12
"""

import asyncio
import logging
import os
from typing import Any

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from custom.output.telegram_commands import handle_command
from custom.utils.db import get_subscribers, upsert_subscriber

logger = logging.getLogger(__name__)

# Telegram message length limit
_MAX_MESSAGE_LENGTH = 4096

# Commands that require admin privileges
_ADMIN_COMMANDS = {"adduser", "removeuser", "subscribers"}


class TelegramBot:
    """Wraps python-telegram-bot Application for the signal bot.

    See docs/sub-specs/SS-18.md §12

    Args:
        config: Full settings dict.
        db_path: Path to SQLite database.
        health_monitor: Optional HealthMonitor for /health and /debug commands.
        scheduler: Optional SignalBotScheduler for /debug job stats.
    """

    def __init__(
        self, config: dict, db_path: str,
        health_monitor: Any = None, scheduler: Any = None,
    ) -> None:
        self._config = config
        self._db_path = db_path
        self._health_monitor = health_monitor
        self._scheduler = scheduler
        self._chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
        self._token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._app: Application | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def _is_admin(self, update: Update) -> bool:
        """Check if the message is from the admin chat."""
        if not self._chat_id:
            return True
        return str(update.effective_chat.id) == self._chat_id

    def _authorized(self, update: Update) -> bool:
        """Check if the message is from an authorized subscriber."""
        if not self._chat_id:
            return True
        chat_id_str = str(update.effective_chat.id)
        if chat_id_str == self._chat_id:
            return True
        subscribers = get_subscribers(self._db_path)
        return chat_id_str in subscribers

    async def _handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Generic command handler that dispatches to handle_command.

        See docs/sub-specs/SS-18.md §12
        """
        if not self._authorized(update):
            return

        command = update.message.text.split()[0].lstrip("/").split("@")[0]

        # Gate admin-only commands
        if command in _ADMIN_COMMANDS and not self._is_admin(update):
            await update.message.reply_text("This command is admin-only.")
            return

        args = update.message.text.split(maxsplit=1)[1] if " " in update.message.text else ""
        response = handle_command(
            command, args, self._db_path, self._config,
            health_monitor=self._health_monitor, scheduler=self._scheduler,
        )
        for chunk in _split_message(response):
            await update.message.reply_text(chunk)

    async def send_message(self, text: str, chat_id: str | None = None) -> None:
        """Send a message to a specific chat or broadcast to all subscribers.

        See docs/sub-specs/SS-18.md §12

        Args:
            text: Message text to send.
            chat_id: Specific chat ID, or None to broadcast to all subscribers.
        """
        if not self._app:
            logger.warning("Cannot send message — bot not initialized")
            return

        if chat_id:
            targets = [chat_id]
        else:
            targets = get_subscribers(self._db_path)
            if not targets:
                logger.warning("No subscribers to broadcast to")
                return

        for target in targets:
            try:
                for chunk in _split_message(text):
                    await self._app.bot.send_message(chat_id=target, text=chunk)
            except Exception as e:
                logger.error("Failed to send message to %s: %s", target, e)

    def broadcast_sync(self, text: str) -> None:
        """Thread-safe wrapper to broadcast a message from a non-async context.

        Uses asyncio.run_coroutine_threadsafe() to bridge from the scheduler
        thread to the bot's event loop.

        See docs/sub-specs/SS-18.md §12

        Args:
            text: Message text to broadcast to all subscribers.
        """
        if not self._loop or self._loop.is_closed():
            logger.warning("Cannot broadcast — event loop not available")
            return

        future = asyncio.run_coroutine_threadsafe(
            self.send_message(text), self._loop
        )
        try:
            future.result(timeout=30)
        except Exception as e:
            logger.error("broadcast_sync failed: %s", e)

    def _ensure_admin_subscriber(self) -> None:
        """Auto-add the admin chat ID as a subscriber on startup.

        See docs/sub-specs/SS-18.md §12
        """
        if self._chat_id:
            added = upsert_subscriber(self._db_path, self._chat_id, added_by="system")
            if added:
                logger.info("Admin %s auto-added as subscriber", self._chat_id)

    async def _post_init(self, application: Application) -> None:
        """Callback invoked after the Application is fully initialized.

        Captures the running event loop for use by broadcast_sync().
        Sends any queued preflight message.
        """
        self._loop = asyncio.get_running_loop()
        logger.info("Event loop captured for broadcast bridge")

        # Send queued preflight report if present
        msg = getattr(self, "_pending_preflight_message", None)
        if msg:
            await self.send_message(msg)
            del self._pending_preflight_message

    def start(self) -> None:
        """Build and start the Telegram bot polling in background.

        See docs/sub-specs/SS-18.md §12
        """
        if not self._token:
            logger.warning("TELEGRAM_BOT_TOKEN not set — Telegram bot disabled")
            return

        self._app = (
            Application.builder()
            .token(self._token)
            .post_init(self._post_init)
            .build()
        )

        commands = [
            "start", "help", "signal", "breakdown", "levels",
            "entry", "risk", "regime", "health", "debug", "macro",
            "performance", "ai",
            "adduser", "removeuser", "subscribers",
        ]
        for cmd in commands:
            self._app.add_handler(CommandHandler(cmd, self._handle))

        logger.info("Starting Telegram bot polling...")
        self._app.run_polling(drop_pending_updates=True)

    def stop(self) -> None:
        """Stop the Telegram bot.

        See docs/sub-specs/SS-18.md §12
        """
        if self._app:
            self._app.stop_running()
            logger.info("Telegram bot stopped")


def _split_message(text: str) -> list[str]:
    """Split a message into chunks that fit Telegram's 4096 char limit.

    Args:
        text: Full message text.

    Returns:
        List of message chunks, each <= 4096 chars.
    """
    if len(text) <= _MAX_MESSAGE_LENGTH:
        return [text]

    chunks = []
    while text:
        if len(text) <= _MAX_MESSAGE_LENGTH:
            chunks.append(text)
            break
        # Try to split at a newline boundary
        split_at = text.rfind("\n", 0, _MAX_MESSAGE_LENGTH)
        if split_at <= 0:
            split_at = _MAX_MESSAGE_LENGTH
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks
