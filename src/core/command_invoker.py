# src/core/command_invoker.py
import traceback
from src.core.command import Command
from src import logger

class CommandInvoker:
    """Generic command invoker for all services"""

    def __init__(self):
        self.commands = {}

    def register_command(self, event_type, command: Command):
        """Register a command for an event type"""
        if event_type is None:
            raise ValueError("event_type is REQUIRED")
        if command is None:
            raise ValueError("command is REQUIRED")
        if not isinstance(command, Command):
            raise ValueError("command must be an instance of Command")

        if event_type not in self.commands:
            self.commands[event_type] = []
        self.commands[event_type].append(command)

    def execute_command(self, event_type, event):
        """Execute all commands registered for the given event type"""
        if event_type is None:
            raise ValueError("event_type is REQUIRED")
        if event is None:
            raise ValueError("event is REQUIRED")

        commands = self.commands.get(event_type, [])
        for command in commands:
            try:
                command.execute(event)
            except Exception as e:
                logger.error(f"Error executing command {command.__class__.__name__} for event {event_type}: {e}")
                logger.error(f"Stack trace: {traceback.format_exc()}")

                error_message = f"{command.__class__.__name__} failed : {str(e)} : event {event_type}"
                command.application_context.state_manager.sendTelegramMessage(error_message)