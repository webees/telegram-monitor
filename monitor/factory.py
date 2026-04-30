"""监控器工厂"""

from typing import Dict, Type, Optional

from core.model import (
    BaseMonitorConfig, KeywordConfig, FileConfig,
    ButtonConfig, AllMessagesConfig, AIMonitorConfig, ImageButtonConfig
)
from .base import BaseMonitor
from .keyword import KeywordMonitor
from .ai import AIMonitor


class MonitorFactory:

    def __init__(self):
        self._registry: Dict[Type, Type] = {}
        self._init_defaults()

    def _init_defaults(self):
        self._registry[KeywordConfig]      = KeywordMonitor
        self._registry[AIMonitorConfig]    = AIMonitor

        from .file         import FileMonitor
        from .button       import ButtonMonitor
        from .all          import AllMessagesMonitor
        from .image_button import ImageButtonMonitor

        self._registry[FileConfig]         = FileMonitor
        self._registry[ButtonConfig]       = ButtonMonitor
        self._registry[AllMessagesConfig]  = AllMessagesMonitor
        self._registry[ImageButtonConfig]  = ImageButtonMonitor

    def register(self, cfg_type: Type, cls: Type):
        self._registry[cfg_type] = cls

    def create_monitor(self, config: BaseMonitorConfig) -> Optional[BaseMonitor]:
        cls = self._registry.get(type(config))
        if not cls:
            return None
        try:
            return cls(config)
        except Exception:
            return None


monitor_factory = MonitorFactory()