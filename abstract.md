# GreenCode Constitution: Automated Energy Optimization of Software via Constitutionally-Guided LLM Agents

## Abstract

We present GreenCode Constitution, an agentic framework that equips Large Language Models (LLMs) with a hierarchy of energy-efficiency principles for automatically detecting and refactoring energy anti-patterns in existing codebases. Rather than relying on ad hoc prompting, the agent evaluates candidate refactorings against a rubric spanning e.g., algorithmic complexity, memory behavior, infrastructure utilization, to ensure optimizations are principled and consistent. We evaluate on open-source projects including LLM inference engines, demonstrating that LLMs can meaningfully optimize the software that runs LLMs: the agent achieved a 4.2% energy reduction on llama.cpp and 3.1% on vLLM, alongside gains of 5.5-8.3% on PostgreSQL, Redis, and Python workloads.
