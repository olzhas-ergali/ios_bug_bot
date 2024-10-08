from contextvars import ContextVar


log_info_context: ContextVar[list] = ContextVar('log_info_context')