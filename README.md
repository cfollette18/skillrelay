# SkillRelay

An agent-agnostic MCP server that turns observed workflows into versioned, evidence-linked skills. Bring your agent and model; SkillRelay supplies tracing, durable learning jobs, evaluation gates, human review, and distribution.

**Under active development.** Human review is the default. Automatic activation requires passing checks, trusted evaluation, and the configured evidence-confidence threshold. Confidence is a rubric score, not a probability or a demonstrated performance improvement.

Single-agent and externally orchestrated multi-agent workflows share the same trace graph. SkillRelay does not schedule agents. No Langfuse account or server-side model key is required.
