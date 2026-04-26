#!/usr/bin/env python3
"""
Interactive CLI for the Payment Collection Agent.

Run:  python cli.py
"""

import sys
import io

# Force UTF-8 on Windows to prevent garbled output with ₹ and other symbols
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from src.agent import Agent


def main():
    agent = Agent()
    print("=" * 60)
    print("  Payment Collection Agent — Interactive CLI")
    print("  Type 'quit' or 'exit' to end the session.")
    print("=" * 60)
    print()

    # Initial greeting
    response = agent.next("")
    print(f"Agent: {response['message']}")
    print()

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nSession ended by user. Goodbye!")
            break

        if user_input.lower() in ("quit", "exit"):
            print("\nSession ended. Goodbye!")
            break

        if not user_input:
            continue

        response = agent.next(user_input)
        print(f"\nAgent: {response['message']}\n")


if __name__ == "__main__":
    main()
