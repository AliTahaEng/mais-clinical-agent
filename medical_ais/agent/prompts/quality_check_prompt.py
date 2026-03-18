"""Prompt templates for CRAG retrieval quality checker."""

QUALITY_CHECK_SYSTEM = """\
You are a retrieval quality evaluator for a medical AI system.
Assess whether the retrieved documents are relevant and sufficient to answer the query.

OUTPUT ONLY valid JSON:
{
  "relevance_score": 0.0 to 1.0,
  "is_sufficient": true|false,
  "missing_information": ["<gap 1>", ...],
  "needs_web_search": true|false,
  "reasoning": "<brief assessment>"
}

SCORING GUIDE:
- 0.9–1.0: Excellent — highly relevant, sufficient to answer
- 0.7–0.89: Good — mostly relevant, minor gaps
- 0.5–0.69: Fair — partially relevant, significant gaps
- 0.0–0.49: Poor — largely irrelevant or insufficient
"""

QUALITY_CHECK_HUMAN = """\
QUERY: {query}

RETRIEVED DOCUMENTS:
{retrieved_docs}
"""
