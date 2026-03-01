# GreenCode Constitution: Principles for AI Agents to Improve Code Efficiency

## Abstract

We present GreenCode Constitution, an agentic framework that equips Large Language Models (LLMs) with a hierarchy of energy-efficiency principles for automatically detecting and refactoring energy anti-patterns in existing codebases. Rather than relying on ad hoc prompting, the agent evaluates candidate refactorings against a rubric spanning e.g., algorithmic complexity, memory behavior, infrastructure utilization, to ensure optimizations are principled and consistent. We evaluate on open-source projects including an LLM inference engine, demonstrating that LLMs can meaningfully optimize the software that runs LLMs: the agent achieved a 6\% GPU energy reduction on llama.cpp through CUDA kernel optimizations, 13.5\% on FFmpeg 4K transcoding, 32.5\% on data synthesis, and 21\% on algorithmic scenarios across six languages.
