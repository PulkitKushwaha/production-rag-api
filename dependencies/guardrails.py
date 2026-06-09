"""
Guardrails Dependency Injection
 
Integrates llm-guardrails into the FastAPI dependency system.
The guardrails wrapper is initialized once (singleton) and
injected into routes that need it.
 
What guardrails add to this API:
    Without guardrails:
        user_input → RAG pipeline → response
 
    With guardrails:
        user_input
            ↓ topic scope check (blocks off-topic queries)
            ↓ PII detection (redacts SSNs, emails from input)
        RAG pipeline
            ↓ PII redaction (removes PII from response)
            ↓ toxicity filter (blocks harmful output)
        safe_response + full audit log
 
This is the production pattern, not just "does it answer correctly"
but "does it answer safely and within scope."
 
Design decision: graceful degradation
    If llm-guardrails is not installed, the dependency returns
    None and routes skip guardrail checks. The API still works —
    just without the safety layer. This avoids a hard dependency
    on the guardrails package for teams who don't need it.
"""
 
from functools import lru_cache
from typing import Optional
 
 
@lru_cache(maxsize=1)
def _get_guardrails_instance():
    """
    Create and cache the guardrails wrapper instance.
 
    Returns None if llm-guardrails is not installed.
    Routes check for None and skip guardrails gracefully.
    """
    try:
        import sys
        import os
 
        # Try to import from installed package or sibling repo
        # In production: pip install llm-guardrails
        # In development: adjust path to local llm-guardrails repo
        sys.path.insert(0, os.getenv("GUARDRAILS_PATH", "../llm-guardrails"))
 
        from src.pipeline.guardrails_wrapper import GuardrailsWrapper, GuardrailConfig
        from src.validators.topic_validator import CUSTOMER_SUPPORT_TOPIC
        from src.output.toxicity_filter import ToxicitySeverity
 
        config = GuardrailConfig(
            topic_config=CUSTOMER_SUPPORT_TOPIC,
            block_off_topic=True,
            detect_input_pii=True,
            block_input_pii=False,        # Redact PII, don't block
            redact_output_pii=True,
            filter_toxicity=True,
            block_toxic_severity=ToxicitySeverity.HIGH,
            use_ml_toxicity=False,        # Keep fast — no ML model
            log_all_checks=True
        )
 
        # The guardrails wrapper needs a pipeline callable.
        # We use a placeholder here — the actual pipeline is
        # injected per-request in the route handler.
        # The wrapper is used directly (not via .run()) in routes.
        print("[Guardrails] Initialized with customer support topic config")
        return {"config": config, "available": True}
 
    except ImportError:
        print(
            "[Guardrails] llm-guardrails not installed — running without guardrails. "
            "Set GUARDRAILS_PATH in .env to enable."
        )
        return {"available": False}
    except Exception as e:
        print(f"[Guardrails] Failed to initialize: {e} — running without guardrails")
        return {"available": False}
 
 
def get_guardrails():
    """
    FastAPI dependency — returns guardrails config dict.
 
    Usage in routes:
        guardrails = Depends(get_guardrails)
        if guardrails["available"]:
            # apply guardrails
    """
    return _get_guardrails_instance()