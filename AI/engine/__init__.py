"""
🤖 AI Engine - المحرك الرئيسي للمساعد الذكي
"""

# Re-export main functions
from AI.engine.ai_service import (
    ai_chat_with_search,
    gather_system_context,
    get_system_setting
)

__all__ = [
    'ai_chat_with_search',
    'gather_system_context',
    'get_system_setting'
]
