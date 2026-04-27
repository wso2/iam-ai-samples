# Agents Package
"""
A2A Protocol Agents.

Individual agents are imported lazily to avoid cross-module dependency 
issues (e.g. vercel_ai_sdk, crewai, google-adk not installed in all envs).
Import directly from the sub-package when needed:
  from agents.hr_agent import HRAgent
  from agents.it_agent import ITAgent
  etc.
"""
