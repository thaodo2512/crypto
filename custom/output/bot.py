"""Telegram bot runner — connects command handlers to python-telegram-bot.

See docs/sub-specs/SS-18.md §12
"""

import logging
import os
from typing import Any

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from custom.output.telegram_commands import handle_command

logger = logging.getLogger(__name__)


class TelegramBot:
    """Wraps python-telegram-bot Application for the signal bot.

    See docs/sub-specs/SS-18.md §12

    Args:
        config: Full settings dict.
        db_path: Path to SQLite database.
    """

    def __init__(self, config: dict, db_path: str) -> None:
        self._config = config
        self._db_path = db_path
        self._chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
        self._token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._app: Application | None = None

    def _authorized(self, update: Update) -> bool:
        """Check if the message is from the authorized chat."""
        if not self._chat_id:
            return True
        return str(update.effective_chat.id) == self._chat_id

    async def _handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Generic command handler that dispatches to handle_command.

        See docs/sub-specs/SS-18.md §12
        """
        if not self._authorized(update):
            return

        command = update.message.text.split()[0].lstrip("/").split("@")[0]
        args = update.message.text.split(maxsplit=1)[1] if " " in update.message.text else ""
        response = handle_command(command, args, self._db_path, self._config)
        await update.message.reply_text(response)

    async def send_message(self, text: str) -> None:
        """Send a message to the configured chat ID.

        See docs/sub-specs/SS-18.md §12

        Args:
            text: Message text to send.
        """
        if not self._app or not self._chat_id:
            logger.warning("Cannot send message — bot not initialized or no chat ID")
            return
        try:
            await self._app.bot.send_message(chat_id=self._chat_id, text=text)
        except Exception as e:
            logger.error("Failed to send Telegram message: %s", e)

    def start(self) -> None:
        """Build and start the Telegram bot polling in background.

        See docs/sub-specs/SS-18.md §12
        """
        if not self._token:
            logger.warning("TELEGRAM_BOT_TOKEN not set — Telegram bot disabled")
            return

        self._app = Application.builder().token(self._token).build()

        commands = [
            "start", "help", "signal", "breakdown", "levels",
            "entry", "risk", "regime", "health", "macro",
            "performance", "ai",
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
