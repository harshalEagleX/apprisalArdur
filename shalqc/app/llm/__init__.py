"""app.llm — SHALqc.md §10 LLM subsystem. Public surface: the client factory,
grounding gate, tier-2 judge, tier-3 verify pass, and the reply validator."""
from app.llm.client import LLMCall, LLMClient, get_client  # noqa: F401
from app.llm.grounding import is_grounded  # noqa: F401
from app.llm.judge import Classification, classify_narrative  # noqa: F401
from app.llm.verify_pass import verify_pass  # noqa: F401

__version__ = "lcl-1.0.0"
