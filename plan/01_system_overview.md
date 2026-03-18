# 01 — System Overview

## System Name
**Medical Autonomous Intelligence System (MAIS)**

---

## Vision

A production-grade AI system that acts as an intelligent clinical decision support layer inside a hospital or healthcare environment. It does not replace doctors — it augments them by catching what they cannot manually trace across thousands of documents, detecting dangerous combinations before they harm patients, and executing safe, approved actions directly into the clinical workflow.

---

## The Core Problem It Solves

A doctor managing 20+ patients at once cannot:
- Manually cross-reference a new prescription against 8 current medications across 5 conditions
- Trace all clinical studies about a specific drug+condition combination in real time
- Know about every relevant clinical trial a patient qualifies for
- Catch all cascading risk factors before they become emergencies

Current systems (EHR drug-interaction checkers) only do flat lookups — they do not reason across interconnected medical knowledge. They miss combinations. They miss context. They miss relationships.

**MAIS solves this by reasoning across structured medical knowledge graphs.**

---

## What the System Can Do

### Query Capabilities
- Answer complex multi-hop medical questions
- Trace drug → enzyme → condition relationships
- Connect symptoms → conditions → treatments across thousands of papers
- Find corpus-wide patterns across all medical literature
- Provide answers with full source citations and confidence scores

### Monitoring Capabilities
- Automatically trigger on new prescription entries
- Monitor lab result arrivals and flag abnormalities in context
- Watch vital sign thresholds and reason about their significance
- Detect patient deterioration patterns across multiple signals

### Reasoning Capabilities
- Multi-hop traversal: Drug A → metabolized by Enzyme X → inhibited by Drug B → risk
- Community-level synthesis: what does all literature say about this combination?
- Self-correction: if retrieved evidence is weak, re-retrieves before answering
- Hallucination detection: every claim in answer verified against retrieved evidence

### Action Capabilities
- TIER 1 (Low Risk): Auto-execute informational actions — log, flag, notify
- TIER 2 (Medium Risk): Propose action to doctor with full reasoning — wait for approval
- TIER 3 (High/Critical Risk): Alert immediately, escalate, block action pending human review
- Integrate with EHR systems via FHIR API (Epic, Cerner, OpenMRS)

### Memory & Continuity
- Remembers full conversation context across sessions per patient
- Tracks what actions were taken and their outcomes
- Learns from doctor overrides to improve future recommendations
- Full immutable audit trail for every decision

---

## What the System Does NOT Do

- Does NOT make final clinical decisions autonomously
- Does NOT take irreversible actions without explicit human approval
- Does NOT replace doctors — it works for them
- Does NOT operate below the confidence threshold without escalating
- Does NOT store patient data outside of the configured secure environment

---

## System Inputs

| Input Type | Source | Trigger |
|---|---|---|
| Manual query | Doctor via API/UI | On demand |
| New prescription | EHR event webhook | Automatic |
| Lab result | EHR event webhook | Automatic |
| Vital sign alert | EHR monitoring | Automatic |
| Patient admission | EHR event webhook | Automatic |
| New medical literature | Scheduled pipeline | Periodic (daily) |

---

## System Outputs

| Output Type | Destination | Risk Level |
|---|---|---|
| Informational alert | Doctor dashboard / notification | Low — auto |
| Drug interaction warning | EHR patient record + doctor | Medium — approval |
| Clinical recommendation | EHR care plan | Medium — approval |
| Emergency escalation | Doctor pager + charge nurse | High — mandatory human |
| Audit log entry | Compliance database | All — automatic |
| Answer with citations | API response | All — informational |

---

## Success Criteria

| Metric | Target |
|---|---|
| Drug interaction detection accuracy | > 92% |
| False positive rate | < 8% |
| Query response time (P95) | < 8 seconds |
| Action execution after approval | < 2 seconds |
| Audit trail completeness | 100% of all actions |
| System availability | > 99.5% |
| Hallucination rate (Self-RAG verified) | < 3% |
| CRAG escalation rate (bad retrieval caught) | Track and minimize |

---

## System Users

| User | Role | Interaction |
|---|---|---|
| Attending Physician | Primary decision maker | Receives alerts, approves/rejects actions |
| Resident Doctor | Clinical queries | Asks complex questions, receives guidance |
| Pharmacist | Medication review | Receives drug interaction alerts |
| Nurse | Monitoring | Receives vital sign + lab context alerts |
| Clinical Admin | Compliance | Reviews audit trail |
| System Admin | Operations | Configures thresholds, manages knowledge base |

---

## Constraints

- All patient data must be de-identified before entering the RAG pipeline
- No patient PII stored in the vector store or knowledge graph
- All actions require idempotency keys — no duplicate executions
- System must degrade gracefully — if graph DB is unavailable, fall back to vector search
- Every external API call must have circuit breaker protection
- Confidence threshold for autonomous action: minimum 0.80
- Maximum reasoning loop iterations: 5 (prevent infinite loops)
- Maximum graph traversal hops: 3 (prevent combinatorial explosion)
