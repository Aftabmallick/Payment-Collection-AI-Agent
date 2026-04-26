"""
Root-level agent module — re-exports the Agent class for evaluation compatibility.

Usage:
    from agent import Agent
    agent = Agent()
    response = agent.next("Hi")
"""

from src.agent import Agent

__all__ = ["Agent"]
