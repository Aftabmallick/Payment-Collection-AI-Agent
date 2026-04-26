#!/usr/bin/env python3
"""
Evaluation framework for the Payment Collection Agent.

Runs scripted conversation scenarios and validates agent behavior at each turn.
Measures: correctness, state transitions, tool-call accuracy, and edge-case handling.

Run:  python evaluate.py
"""

import sys
import io
from dataclasses import dataclass
from src.agent import Agent
from src.nodes import determine_next_node

# Force UTF-8 for Windows console
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------


@dataclass
class TurnCheck:
    """One turn: user says something, then we check the agent's response."""

    user_input: str
    expect_contains: list[str] = None
    expect_not_contains: list[str] = None
    expect_node: str = None

    def __post_init__(self):
        self.expect_contains = self.expect_contains or []
        self.expect_not_contains = self.expect_not_contains or []


@dataclass
class TestScenario:
    name: str
    description: str
    turns: list[TurnCheck]


# ---------------------------------------------------------------------------
# Test scenarios
# ---------------------------------------------------------------------------

SCENARIOS: list[TestScenario] = [
    # ===== 1. HAPPY PATH — full payment =====
    TestScenario(
        name="Happy Path - Full Payment",
        description="ACC1001: correct name + DOB, valid card, full balance payment.",
        turns=[
            TurnCheck(
                user_input="Hi",
                expect_contains=["account"],
                expect_node="greeting_and_account",
            ),
            TurnCheck(
                user_input="My account ID is ACC1001",
                expect_contains=["name"],
                expect_node="collect_name",
            ),
            TurnCheck(
                user_input="Nithin Jain",
                expect_contains=["date of birth", "aadhaar", "pincode"],
                expect_node="collect_secondary_factor",
            ),
            TurnCheck(
                user_input="DOB is 1990-05-14",
                expect_contains=["verified", "1,250.75"],
                expect_node="payment_decision",
            ),
            TurnCheck(
                user_input="Yes, I'd like to pay the full amount",
                expect_contains=["1,250.75", "card"],
                expect_node="collect_card_details",
            ),
            TurnCheck(
                user_input="Nithin Jain",
                expect_contains=["card number"],
            ),
            TurnCheck(
                user_input="4532015112830366",
                expect_contains=["cvv"],
            ),
            TurnCheck(
                user_input="123",
                expect_contains=["expiry"],
            ),
            TurnCheck(
                user_input="12/2027",
                expect_contains=["successful", "transaction"],
                expect_node="recap_and_close",
            ),
        ],
    ),
    # ===== 2. PARTIAL PAYMENT =====
    TestScenario(
        name="Partial Payment",
        description="ACC1001: verify with Aadhaar, pay 500 out of 1,250.75.",
        turns=[
            TurnCheck(user_input="Hello"),
            TurnCheck(user_input="ACC1001"),
            TurnCheck(user_input="Nithin Jain"),
            TurnCheck(
                user_input="Aadhaar last 4: 4321",
                expect_contains=["verified", "1,250.75"],
            ),
            TurnCheck(
                user_input="I'd like to pay 500",
                expect_contains=["500.00"],
                expect_node="collect_card_details",
            ),
            TurnCheck(user_input="Nithin Jain"),
            TurnCheck(user_input="4532015112830366"),
            TurnCheck(user_input="123"),
            TurnCheck(
                user_input="12/2027",
                expect_contains=["successful", "500.00"],
            ),
        ],
    ),
    # ===== 3. VERIFICATION FAILURE — wrong name =====
    TestScenario(
        name="Verification Failure - Wrong Name",
        description="ACC1001: wrong name then wrong secondary factors until lockout.",
        turns=[
            TurnCheck(user_input="Hi"),
            TurnCheck(user_input="ACC1001"),
            TurnCheck(
                user_input="John Doe",
                expect_node="collect_secondary_factor",
            ),
            TurnCheck(
                user_input="1990-05-14",
                expect_contains=["does not match", "2"],
            ),
            # Name was reset, user must provide name again — send name + factor
            TurnCheck(
                user_input="John Doe",
                expect_node="collect_secondary_factor",
            ),
            TurnCheck(
                user_input="4321",
                expect_contains=["does not match", "1"],
            ),
            TurnCheck(
                user_input="John Doe",
                expect_node="collect_secondary_factor",
            ),
            TurnCheck(
                user_input="400001",
                expect_contains=["exceeded", "locked"],
                expect_node="closed",
            ),
        ],
    ),
    # ===== 4. VERIFICATION FAILURE — wrong secondary factor =====
    TestScenario(
        name="Verification Failure - Wrong Secondary Factor",
        description="ACC1001: correct name but wrong DOB/Aadhaar/pincode 3 times.",
        turns=[
            TurnCheck(user_input="Hi"),
            TurnCheck(user_input="ACC1001"),
            TurnCheck(user_input="Nithin Jain"),
            TurnCheck(
                user_input="DOB is 1991-01-01",
                expect_contains=["does not match", "2"],
            ),
            # Name was correct so it's preserved — only need to re-enter secondary factor
            TurnCheck(
                user_input="1234",
                expect_contains=["does not match", "1"],
            ),
            TurnCheck(
                user_input="999999",
                expect_contains=["exceeded", "locked"],
            ),
        ],
    ),
    # ===== 5. PAYMENT FAILURE — invalid card number =====
    TestScenario(
        name="Payment Failure - Invalid Card",
        description="ACC1001: verified, provide an invalid (non-Luhn) card number.",
        turns=[
            TurnCheck(user_input="Hi"),
            TurnCheck(user_input="ACC1001"),
            TurnCheck(user_input="Nithin Jain"),
            TurnCheck(user_input="1990-05-14"),
            TurnCheck(user_input="Yes, full amount"),
            TurnCheck(user_input="Nithin Jain"),
            TurnCheck(
                user_input="1234567890123456",
                expect_contains=["invalid", "card number"],
            ),
        ],
    ),
    # ===== 6. PAYMENT FAILURE — expired card =====
    TestScenario(
        name="Payment Failure - Expired Card",
        description="ACC1001: verified, provide expired card details.",
        turns=[
            TurnCheck(user_input="Hi"),
            TurnCheck(user_input="ACC1001"),
            TurnCheck(user_input="Nithin Jain"),
            TurnCheck(user_input="1990-05-14"),
            TurnCheck(user_input="Yes, pay full"),
            TurnCheck(user_input="Nithin Jain"),
            TurnCheck(user_input="4532015112830366"),
            TurnCheck(user_input="123"),
            TurnCheck(
                user_input="01/2020",
                expect_contains=["expired"],
            ),
        ],
    ),
    # ===== 7. ACCOUNT NOT FOUND =====
    TestScenario(
        name="Account Not Found",
        description="Provide a non-existent account ID.",
        turns=[
            TurnCheck(user_input="Hi"),
            TurnCheck(
                user_input="ACC9999",
                expect_contains=["no account", "ACC9999"],
                expect_node="greeting_and_account",
            ),
        ],
    ),
    # ===== 8. ZERO BALANCE ACCOUNT =====
    TestScenario(
        name="Zero Balance Account",
        description="ACC1003: verify then see zero balance.",
        turns=[
            TurnCheck(user_input="Hi"),
            TurnCheck(user_input="ACC1003"),
            TurnCheck(user_input="Priya Agarwal"),
            TurnCheck(
                user_input="1992-08-10",
                expect_contains=["verified", "no outstanding balance"],
                expect_node="closed",
            ),
        ],
    ),
    # ===== 9. LEAP YEAR DOB — ACC1004 =====
    TestScenario(
        name="Leap Year DOB Edge Case",
        description="ACC1004: Rahul Mehta with DOB 1988-02-29 (valid leap year).",
        turns=[
            TurnCheck(user_input="Hi"),
            TurnCheck(user_input="ACC1004"),
            TurnCheck(user_input="Rahul Mehta"),
            TurnCheck(
                user_input="1988-02-29",
                expect_contains=["verified", "3,200.50"],
                expect_node="payment_decision",
            ),
        ],
    ),
    # ===== 10. ACCOUNT ID IN GREETING =====
    TestScenario(
        name="Out-of-Order: Account ID in Greeting",
        description="User provides account ID in the first message.",
        turns=[
            TurnCheck(
                user_input="Hi, my account ID is ACC1001",
                expect_contains=["name"],
                expect_node="collect_name",
            ),
        ],
    ),
    # ===== 11. VERIFICATION WITH PINCODE =====
    TestScenario(
        name="Verification with Pincode",
        description="ACC1001: verify using pincode as secondary factor.",
        turns=[
            TurnCheck(user_input="Hello"),
            TurnCheck(user_input="ACC1001"),
            TurnCheck(user_input="Nithin Jain"),
            TurnCheck(
                user_input="Pincode is 400001",
                expect_contains=["verified", "1,250.75"],
            ),
        ],
    ),
    # ===== 12. LONG NAME — ACC1002 =====
    TestScenario(
        name="Long Name - ACC1002",
        description="ACC1002: Rajarajeswari Balasubramaniam — tests exact long name matching.",
        turns=[
            TurnCheck(user_input="Hi"),
            TurnCheck(user_input="ACC1002"),
            TurnCheck(user_input="Rajarajeswari Balasubramaniam"),
            TurnCheck(
                user_input="DOB is 1985-11-23",
                expect_contains=["verified", "540.00"],
            ),
        ],
    ),
    # ===== 13. PAYMENT DECLINE =====
    TestScenario(
        name="User Declines Payment",
        description="ACC1001: verified, user declines to pay.",
        turns=[
            TurnCheck(user_input="Hi"),
            TurnCheck(user_input="ACC1001"),
            TurnCheck(user_input="Nithin Jain"),
            TurnCheck(user_input="1990-05-14"),
            TurnCheck(
                user_input="No, I don't want to pay right now",
                expect_contains=["1,250.75"],
                expect_node="closed",
            ),
        ],
    ),
    # ===== 14. SENSITIVE DATA NOT EXPOSED =====
    TestScenario(
        name="No Sensitive Data Exposure on Failure",
        description=": wrong name — verify agent doesn't reveal DOB/Aadhaar/pincode.",
        turns=[
            TurnCheck(user_input="Hi"),
            TurnCheck(user_input="ACC1001"),
            TurnCheck(user_input="Amit Sharma"),
            TurnCheck(
                user_input="1990-05-14",
                expect_contains=["does not match"],
                expect_not_contains=["4321", "400001", "Nithin"],
            ),
        ],
    ),
    # ===== 15. CLOSED SESSION REJECTS INPUT =====
    TestScenario(
        name="Closed Session Rejects Input",
        description="After lockout, further input returns a static 'session ended' message.",
        turns=[
            TurnCheck(user_input="Hi"),
            TurnCheck(user_input="ACC1001"),
            TurnCheck(user_input="Amit Sharma"),
            TurnCheck(user_input="1990-05-14"),
            TurnCheck(user_input="Amit Sharma"),
            TurnCheck(user_input="4321"),
            TurnCheck(user_input="Amit Sharma"),
            TurnCheck(
                user_input="400001",
                expect_contains=["exceeded", "locked"],
            ),
            # Session is now closed — further input should be rejected
            TurnCheck(
                user_input="ACC1001",
                expect_contains=["session", "ended"],
            ),
            TurnCheck(
                user_input="Hello?",
                expect_contains=["session", "ended"],
            ),
        ],
    ),
    # ===== 16. AMOUNT EXCEEDS BALANCE =====
    TestScenario(
        name="Amount Exceeds Balance",
        description="ACC1001: verified, try to pay more than balance.",
        turns=[
            TurnCheck(user_input="Hi"),
            TurnCheck(user_input="ACC1001"),
            TurnCheck(user_input="Nithin Jain"),
            TurnCheck(user_input="1990-05-14"),
            TurnCheck(
                user_input="I want to pay 5000",
                expect_contains=["exceeds"],
            ),
        ],
    ),
    # ===== 17. INPUT SANITIZATION =====
    TestScenario(
        name="Input Sanitization - Long Input",
        description="Agent handles excessively long input without crashing.",
        turns=[
            TurnCheck(
                user_input="A" * 600,
                expect_contains=["account"],
            ),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------


def run_scenario(scenario: TestScenario) -> tuple[bool, list[str]]:
    """Run a single test scenario. Returns (passed, errors)."""
    agent = Agent()
    errors = []

    for i, turn in enumerate(scenario.turns, 1):
        try:
            result = agent.next(turn.user_input)
        except Exception as e:
            errors.append(f"Turn {i}: Exception — {e}")
            import traceback

            traceback.print_exc()
            break

        msg = result.get("message", "")
        msg_lower = msg.lower()

        for substr in turn.expect_contains:
            if substr.lower() not in msg_lower:
                errors.append(
                    f"Turn {i}: Expected '{substr}' in response but not found.\n"
                    f"  User said: '{turn.user_input}'\n"
                    f"  Agent said: '{msg[:300]}...'"
                )

        for substr in turn.expect_not_contains or []:
            if substr.lower() in msg_lower:
                errors.append(
                    f"Turn {i}: Did NOT expect '{substr}' in response.\n"
                    f"  Agent said: '{msg[:300]}...'"
                )

        if turn.expect_node:
            next_node = determine_next_node(agent.state)
            if next_node != turn.expect_node:
                errors.append(
                    f"Turn {i}: Expected next node '{turn.expect_node}' "
                    f"but got '{next_node}'."
                )

    return len(errors) == 0, errors


def run_all():
    """Run all test scenarios and print results."""
    import time

    print("=" * 70)
    print("  Payment Collection Agent — Evaluation Suite")
    print("=" * 70)
    print()

    total = len(SCENARIOS)
    passed_count = 0
    failed_scenarios = []
    total_start = time.time()

    for scenario in SCENARIOS:
        print(f"  [{scenario.name}]")
        print(f"    {scenario.description}")

        sc_start = time.time()
        passed, errors = run_scenario(scenario)
        sc_elapsed = time.time() - sc_start

        if passed:
            print(f"    ✅ PASSED ({sc_elapsed:.1f}s)")
            passed_count += 1
        else:
            print(f"    ❌ FAILED ({len(errors)} error(s), {sc_elapsed:.1f}s)")
            for err in errors:
                print(f"      - {err}")
            failed_scenarios.append(scenario.name)

        print()

    total_elapsed = time.time() - total_start

    print("=" * 70)
    print(f"  Results: {passed_count}/{total} passed")
    if failed_scenarios:
        print(f"  Failed: {', '.join(failed_scenarios)}")
    print("=" * 70)

    print()
    print("Metrics:")
    print(f"  Success rate:    {passed_count / total * 100:.1f}%")
    print(f"  Total scenarios: {total}")
    print(f"  Passed:          {passed_count}")
    print(f"  Failed:          {total - passed_count}")
    print(f"  Total time:      {total_elapsed:.1f}s")
    print(f"  Avg per test:    {total_elapsed / total:.1f}s")

    return passed_count == total


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
