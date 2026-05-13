# Paper Claw Agent Memory

Paper Claw stores durable research data in PostgreSQL through tools. Use DeepAgents runtime state for scratch todos, temporary analysis context, and subagent coordination.

Parsing priority is TeX source first, local OCR second, and LlamaParse fallback third. Search confirmation should update the thread focus unless runtime context explicitly overrides active paper selection.
