import pytest
import time
from google.genai import errors as genai_errors
SELLER_ID  = "6a2fe450e9ea3728609743c3"   # replace
PRODUCT_ID = "6a2fe450e9ea3728609743d4" # replace

from app.agent.dashboard_pipeline import run_dashboard_analysis, run_product_detail
from app.agent.chatbot_pipeline   import run_chat


# --- dashboard card ---

def test_dashboard_analysis_keys():
    result = run_dashboard_analysis(PRODUCT_ID, SELLER_ID, include_gemini=False)
    for key in ("product_id", "return_rate", "anomaly", "risk_signal", "error"):
        assert key in result

def test_dashboard_analysis_risk_signal_with_gemini():
    result = run_dashboard_analysis(PRODUCT_ID, SELLER_ID, include_gemini=True)
    assert result["risk_signal"] in ("High", "Medium", "Low", "Unknown")

def test_dashboard_analysis_bad_product():
    result = run_dashboard_analysis("000000000000000000000000", SELLER_ID)
    # Should not raise — error field may be populated but dict is returned
    assert isinstance(result, dict)


# --- product detail ---

def test_product_detail_returns_dict():
    result = run_product_detail(PRODUCT_ID, SELLER_ID)
    assert isinstance(result, dict)

def test_product_detail_has_sections():
    result = run_product_detail(PRODUCT_ID, SELLER_ID)
    for section in ("overview", "return_reasons", "customer_feedback", "anomalies"):
        assert section in result

def test_product_detail_overview_available():
    result = run_product_detail(PRODUCT_ID, SELLER_ID)
    assert result["overview"]["available"] is True

def test_product_detail_sections_have_available_flag():
    result = run_product_detail(PRODUCT_ID, SELLER_ID)
    for section_key, section_val in result.items():
        if isinstance(section_val, dict):
            assert "available" in section_val, f"Section '{section_key}' missing 'available' key"


# --- chatbot ---

def test_chat_returns_string():
    result = run_chat("What are the top return reasons?", SELLER_ID)
    assert isinstance(result, str)
    assert len(result) > 0
    time.sleep(5) 

def test_chat_out_of_scope():
    result = run_chat("What's the weather in Kochi today?", SELLER_ID)
    assert "only assist" in result.lower() or "return" in result.lower()
    time.sleep(5) 

def test_chat_seller_isolation():
    # Two sellers asking the same question should not produce identical
    # data-referencing responses (basic smoke test)
    r1 = run_chat("How many returns do I have?", SELLER_ID)
    r2 = run_chat("How many returns do I have?", "different_seller_id")
    assert isinstance(r1, str) and isinstance(r2, str)

# Decorator to skip on quota errors
def skip_on_quota(func):
    import functools
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (genai_errors.ClientError, Exception) as e:
            if "429" in str(e) or "503" in str(e) or "RESOURCE_EXHAUSTED" in str(e) or "UNAVAILABLE" in str(e):
                pytest.skip(f"Gemini quota/availability issue: {str(e)[:80]}")
            raise
    return wrapper


@skip_on_quota
def test_chat_returns_string():
    result = run_chat("What are the top return reasons?", SELLER_ID)
    assert isinstance(result, str)
    assert len(result) > 0
    time.sleep(5)

@skip_on_quota
def test_chat_out_of_scope():
    result = run_chat("What's the weather in Kochi today?", SELLER_ID)
    assert "only assist" in result.lower() or "return" in result.lower()
    time.sleep(5)

@skip_on_quota
def test_chat_seller_isolation():
    r1 = run_chat("How many returns do I have?", SELLER_ID)
    r2 = run_chat("How many returns do I have?", "different_seller_id")
    assert isinstance(r1, str) and isinstance(r2, str)
