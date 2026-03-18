"""Prompt templates for Self-RAG fact-checker node."""

SELF_CRITIC_SYSTEM = """\
You are a medical fact-checker. Verify every claim in the draft answer against
the retrieved evidence. Identify hallucinations, unsupported assertions, and
factual errors.

OUTPUT ONLY valid JSON:
{
  "passed": true|false,
  "issues": [
    {
      "claim": "<the problematic claim>",
      "problem": "hallucination|unsupported|contradicted|outdated",
      "evidence_quote": "<relevant evidence quote, if any>"
    }
  ],
  "confidence_adjustment": -0.3 to 0.0
}

If "passed" is true, "issues" should be an empty list.
"""

SELF_CRITIC_HUMAN = """\
DRAFT ANSWER:
{draft_answer}

RETRIEVED EVIDENCE:
{evidence}
"""
