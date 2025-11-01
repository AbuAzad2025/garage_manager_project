"""
🤖 AI Engine - المحرك الرئيسي للمساعد الذكي
════════════════════════════════════════════════════════════════════

هذا الملف المركزي يجمع كل وظائف المساعد الذكي
ويسهّل الاستيراد من أي مكان في النظام

Architecture:
- ai_service.py: المحرك الرئيسي
- ai_database_search.py: البحث في قاعدة البيانات
- ai_conversation.py: المحادثة والذاكرة
- ai_knowledge*.py: قواعد المعرفة
- ai_accounting_professional.py: المحاسبة الاحترافية

Refactored: 2025-11-01
Version: Professional 5.0
"""

# ═══════════════════════════════════════════════════════════════════════════
# CORE SERVICES - الخدمات الأساسية
# ═══════════════════════════════════════════════════════════════════════════

from .ai_service import (
    ai_chat_with_search,
    gather_system_context,
    build_system_message,
    get_system_setting
)

# ═══════════════════════════════════════════════════════════════════════════
# DATABASE SEARCH - البحث في قاعدة البيانات
# ═══════════════════════════════════════════════════════════════════════════

from .ai_database_search import (
    search_database_for_query,
    analyze_query_intent,
    get_time_range
)

# ═══════════════════════════════════════════════════════════════════════════
# CONVERSATION & MEMORY - المحادثة والذاكرة
# ═══════════════════════════════════════════════════════════════════════════

from .ai_conversation import (
    get_or_create_session_memory,
    add_to_memory,
    clear_session_memory,
    get_conversation_context,
    get_local_faq_responses,
    match_local_response,
    get_conversation_stats
)

# ═══════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BASES - قواعد المعرفة
# ═══════════════════════════════════════════════════════════════════════════

from .ai_knowledge import (
    get_knowledge_base,
    analyze_error,
    format_error_response
)

from .ai_knowledge_finance import (
    get_finance_knowledge,
    calculate_palestine_income_tax,
    calculate_vat,
    get_customs_info,
    get_tax_knowledge_detailed
)

from .ai_gl_knowledge import (
    get_gl_knowledge_for_ai,
    explain_gl_entry,
    analyze_gl_batch,
    detect_gl_error,
    suggest_gl_correction,
    explain_any_number,
    trace_transaction_flow
)

from .ai_accounting_professional import (
    get_professional_accounting_knowledge,
    ACCOUNTING_EQUATION,
    DOUBLE_ENTRY_SYSTEM,
    CHART_OF_ACCOUNTS,
    BALANCE_FORMULAS,
    FINANCIAL_STATEMENTS
)

# ═══════════════════════════════════════════════════════════════════════════
# ADVANCED FEATURES - الميزات المتقدمة
# ═══════════════════════════════════════════════════════════════════════════

from .ai_management import (
    save_api_key_encrypted,
    test_api_key,
    list_configured_apis,
    start_training_job,
    get_training_job_status,
    get_live_ai_stats
)

from .ai_self_review import (
    log_interaction,
    check_policy_compliance,
    generate_self_audit_report,
    get_system_status
)

from .ai_auto_discovery import (
    auto_discover_if_needed,
    find_route_by_keyword,
    get_route_suggestions,
    load_system_map,
    build_system_map
)

from .ai_data_awareness import (
    auto_build_if_needed,
    find_model_by_keyword,
    load_data_schema
)

# ═══════════════════════════════════════════════════════════════════════════
# EXPORTS - التصدير الشامل
# ═══════════════════════════════════════════════════════════════════════════

__all__ = [
    # Core Services
    'ai_chat_with_search',
    'gather_system_context',
    'build_system_message',
    'get_system_setting',
    
    # Database Search
    'search_database_for_query',
    'analyze_query_intent',
    'get_time_range',
    
    # Conversation
    'get_or_create_session_memory',
    'add_to_memory',
    'clear_session_memory',
    'get_conversation_context',
    'get_local_faq_responses',
    'match_local_response',
    'get_conversation_stats',
    
    # Knowledge Bases
    'get_knowledge_base',
    'analyze_error',
    'format_error_response',
    'get_finance_knowledge',
    'calculate_palestine_income_tax',
    'calculate_vat',
    'get_customs_info',
    'get_tax_knowledge_detailed',
    
    # GL & Accounting
    'get_gl_knowledge_for_ai',
    'explain_gl_entry',
    'analyze_gl_batch',
    'detect_gl_error',
    'suggest_gl_correction',
    'explain_any_number',
    'trace_transaction_flow',
    'get_professional_accounting_knowledge',
    
    # Advanced
    'save_api_key_encrypted',
    'test_api_key',
    'list_configured_apis',
    'start_training_job',
    'get_training_job_status',
    'get_live_ai_stats',
    'log_interaction',
    'check_policy_compliance',
    'generate_self_audit_report',
    'get_system_status',
    'auto_discover_if_needed',
    'find_route_by_keyword',
    'get_route_suggestions',
    'load_system_map',
    'build_system_map',
    'auto_build_if_needed',
    'find_model_by_keyword',
    'load_data_schema'
]

__version__ = '5.0.0'
__author__ = 'Azad Smart Systems - Ahmed Ghannam'
__description__ = 'Professional AI Accountant Assistant Engine'
