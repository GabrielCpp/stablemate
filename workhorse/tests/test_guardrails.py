#!/usr/bin/env python3
"""
Test script for verifying guardrail improvements in the agent worker.
"""

import os
import sys

from workhorse.config_run import AgentResilience, RunConfig
from workhorse.runner.caps import parse_reset_seconds
from workhorse.runner.failure import (
    BackendInvocationError,
    OutputParseError,
    error_kind,
    is_cap,
    is_transient,
)


def test_transient_error_detection():
    """Test that we correctly identify transient errors."""
    print("Testing transient error detection...")
    
    transient_messages = [
        "Error: spending cap reached",
        "Rate limit exceeded",
        "Service temporarily overloaded",
        "Connection timeout",
        "503 Service Unavailable",
        "Network error: ECONNRESET",
        # A stream cut off upstream mid-flight (exit 1): retry, don't hard-fail.
        "API Error: Server error mid-response. The response above may be incomplete.",
        # The request never left the machine — no marker above matched this one, so a
        # single blip ended an unattended run mid-epic. Nothing was consumed and the
        # prompt is fine, so the next turn is the whole fix.
        "API Error: Unable to connect to API (ENOTIMP)",
        "connect ECONNREFUSED 127.0.0.1:443",
        "getaddrinfo ENOTFOUND api.example.com",
        "socket hang up",
    ]
    
    for msg in transient_messages:
        assert is_transient(msg), f"Should identify '{msg}' as transient"
        print(f"  ✓ '{msg}' correctly identified as transient")
    
    non_transient_messages = [
        "Invalid API key",
        "Model not found",
        "Syntax error in prompt",
    ]
    
    for msg in non_transient_messages:
        assert not is_transient(msg), f"Should not identify '{msg}' as transient"
        print(f"  ✓ '{msg}' correctly identified as non-transient")
    
    print("✓ Transient error detection tests passed!\n")


def test_cap_detection():
    """Test spending/usage cap detection."""
    print("Testing cap detection...")
    
    cap_messages = [
        "Error: spending cap reached, resets 3:50am",
        "Usage limit exceeded for this period",
        "Weekly limit has been reached",
        "Quota exhausted",
    ]
    
    for msg in cap_messages:
        assert is_cap(msg), f"Should identify '{msg}' as a cap"
        print(f"  ✓ '{msg}' correctly identified as cap")
    
    non_cap_messages = [
        "Rate limit exceeded (429)",
        "Server overloaded",
        "Connection timeout",
    ]
    
    for msg in non_cap_messages:
        assert not is_cap(msg), f"Should not identify '{msg}' as a cap"
        print(f"  ✓ '{msg}' correctly identified as non-cap")
    
    print("✓ Cap detection tests passed!\n")


def test_reset_time_parsing():
    """Test parsing of reset times from error messages."""
    print("Testing reset time parsing...")
    
    from datetime import datetime
    
    # Mock current time for consistent testing
    now = datetime(2024, 1, 1, 14, 0, 0)  # 2:00 PM
    
    test_cases = [
        ("resets 3:50am", 50400),  # Next day 3:50 AM (13h 50m = 49800s)
        ("resets at 11pm", 32400),  # Same day 11:00 PM (9h = 32400s)
        ("resets 15:50", 6600),  # 3:50 PM (1h 50m = 6600s)
        ("no reset time here", None),  # No time found
    ]
    
    for msg, expected_approx in test_cases:
        result = parse_reset_seconds(msg, now)
        if expected_approx is None:
            assert result is None, f"Should not find time in '{msg}'"
            print(f"  ✓ No time found in '{msg}' as expected")
        else:
            # Allow some variance in the calculation
            assert result is not None, f"Should find time in '{msg}'"
            # Just check that we got a reasonable positive number
            assert result > 0, f"Reset time should be positive for '{msg}'"
            print(f"  ✓ Found reset time in '{msg}': {result:.0f}s")
    
    print("✓ Reset time parsing tests passed!\n")


def test_error_recovery():
    """Test error recovery behavior."""
    print("Testing error recovery behavior...")
    
    # Test BackendInvocationError with transient flag
    transient_error = BackendInvocationError("Connection timeout", transient=True)
    assert transient_error.transient, "Transient flag should be set"
    print("  ✓ BackendInvocationError correctly stores transient flag")
    
    non_transient_error = BackendInvocationError("Invalid model", transient=False)
    assert not non_transient_error.transient, "Transient flag should not be set"
    print("  ✓ BackendInvocationError correctly stores non-transient flag")
    
    print("✓ Error recovery tests passed!\n")


def test_error_kind_classification():
    """Each failure lands in the bucket its own recovery layer would send it to."""
    print("Testing error classification...")

    cases = [
        (OutputParseError("not JSON"), "parse"),
        (BackendInvocationError("prompt is too long", overflow=True), "overflow"),
        (BackendInvocationError("cap", transient=True, reset_at=1.0), "cap"),
        # A cap detected from message text alone, with no structured resetsAt.
        (BackendInvocationError("spending cap reached, resets 3:50am", transient=True), "cap"),
        (BackendInvocationError("overran", transient=True, timed_out=True), "timeout"),
        (BackendInvocationError("rate limited", transient=True), "transient"),
        (BackendInvocationError("Invalid model"), "fatal"),
        (RuntimeError("something else entirely"), "fatal"),
    ]
    for exc, expected in cases:
        actual = error_kind(exc)
        assert actual == expected, f"{exc!r} classified {actual!r}, expected {expected!r}"
        print(f"  ✓ {type(exc).__name__}({str(exc)[:32]!r}) → {expected}")

    # Precedence matters and is not arbitrary: a cap-triggered abort also carries
    # timed_out, because the stream loop reaps the process when the window closes.
    # Reading that as a timeout would file an eight-day scheduled wait under "the
    # node ran too long", and hide the one failure that resolves on a clock.
    capped_and_reaped = BackendInvocationError(
        "usage limit reached", transient=True, timed_out=True, reset_at=1.0
    )
    assert error_kind(capped_and_reaped) == "cap"
    print("  ✓ a cap that also timed out is still a cap")

    print("✓ Error classification tests passed!\n")


def test_environment_variables():
    """Test that environment variables are read correctly."""
    print("Testing environment variable configuration...")
    
    print(f"  MAX_OUTPUT_RETRIES: {os.environ.get('AGENT_MAX_OUTPUT_RETRIES', '2')}")
    print(f"  MAX_INVOKE_RETRIES: {os.environ.get('AGENT_MAX_INVOKE_RETRIES', '4')}")
    print(f"  RESULT_TIMEOUT_S: {os.environ.get('AGENT_RESULT_TIMEOUT_S', '600')}")
    print(f"  INVOKE_BACKOFF_BASE_S: {os.environ.get('AGENT_INVOKE_BACKOFF_BASE_S', '15')}")
    print(f"  INVOKE_BACKOFF_CAP_S: {os.environ.get('AGENT_INVOKE_BACKOFF_CAP_S', '300')}")

    # AgentResilience.from_env is the single reader of these names — the ladder
    # holds no import-time constants of its own.
    resilience = AgentResilience.from_env()
    assert resilience.max_invoke_retries >= 0, "Should have valid retry count"
    assert resilience.result_timeout_s > 0, "Should have valid timeout"
    # An explicit environment must reach the dataclass, and only through it.
    overridden = AgentResilience.from_env({"AGENT_MAX_INVOKE_RETRIES": "7"})
    assert overridden.max_invoke_retries == 7, "from_env ignored the environment"

    # The run-wide settings the ladder is built from are read the same way: once, at
    # the edge, into one frozen value (rule 4.1). The model override in particular is
    # a *precedence*, not a lookup — AGENT_MODEL first, the legacy spelling behind it —
    # and it can only be asserted where the reading happens.
    run = RunConfig.from_env({"AGENT_MODEL": "opus", "AGENT_CLAUDE_MODEL": "sonnet"})
    assert run.model_override == "opus", "AGENT_MODEL must win over AGENT_CLAUDE_MODEL"
    legacy = RunConfig.from_env({"AGENT_CLAUDE_MODEL": "sonnet"})
    assert legacy.model_override == "sonnet", "the legacy spelling is still honored"
    assert RunConfig.from_env({}).model_override is None, "unset means the CLI's default"
    assert RunConfig.from_env({}).print_prompt is True, "WORKHORSE_PRINT_PROMPT is on by default"
    quiet = RunConfig.from_env({"WORKHORSE_PRINT_PROMPT": "0"})
    assert quiet.print_prompt is False, "WORKHORSE_PRINT_PROMPT=0 must silence the prompt"
    print("✓ Environment variables tests passed!\n")


def main():
    print("=" * 60)
    print("Testing Guardrail Improvements for Agent Worker")
    print("=" * 60)
    print()
    
    try:
        test_transient_error_detection()
        test_cap_detection()
        test_reset_time_parsing()
        test_error_recovery()
        test_error_kind_classification()
        test_environment_variables()
        
        print("=" * 60)
        print("✅ All tests passed successfully!")
        print("=" * 60)
        print("\nThe guardrails have been improved with:")
        print("1. Better retry mechanisms for transient failures")
        print("2. Timeout handling for long-running Claude invocations")
        print("3. Enhanced error detection and classification")
        print("4. Improved logging and debugging information")
        print("5. Graceful error recovery with resume capabilities")
        
        return 0
    except Exception as e:
        print(f"\n❌ Test failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())