# src/core/command.py
from abc import ABC, abstractmethod
from src.core.observer import Subject

class Command(ABC):
    """Generic base command class for all services"""

    def __init__(self, application_context):
        if application_context is None:
            raise ValueError("application_context is REQUIRED")

        self.client = application_context.client
        self.config = application_context.config
        self.subject: Subject = application_context.subject
        self.application_context = application_context
        # Keep state_manager for backward compatibility during transition
        self.state_manager = application_context.state_manager
        # Add database_manager access for commands that need it
        self.database_manager = getattr(application_context, 'database_manager', None)

    @abstractmethod
    def execute(self, event):
        """Execute the command with the given event"""
        pass