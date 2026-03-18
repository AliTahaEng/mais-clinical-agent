# 06 — Phase 1: Data Pipeline

## Purpose
Build the knowledge base — ingest medical documents, extract entities and relationships, build the knowledge graph, detect communities, embed everything. This runs once at setup and then periodically (daily) for new literature.

---

## Pipeline Steps in Order

```
Step 1: Document Ingestion
Step 2: Text Chunking (Parent + Child)
Step 3: Entity Extraction
Step 4: Relationship Extraction
Step 5: Entity Resolution (deduplication)
Step 6: Graph Storage in Neo4j
Step 7: Community Detection (Leiden)
Step 8: Community Summarization
Step 9: Embedding Everything
Step 10: Index to Vector Store + Elasticsearch
```

---

## Step 1: Document Ingestion

**File**: `pipeline/ingestion/document_loader.py`

**Input sources**:
- PubMed articles (via PubMed API or bulk download)
- Clinical guidelines (WHO, NIH, NICE — PDF/HTML)
- Drug databases (DrugBank XML, RxNorm)
- Clinical trial data (ClinicalTrials.gov API)

**What it produces**:
```python
@dataclass
class RawDocument:
    doc_id: str            # UUID
    source: str            # "pubmed" | "drugbank" | "nih_guideline" | "clinical_trial"
    title: str
    content: str           # full text
    metadata: dict         # date, authors, doi, pmid, url
    doc_type: str          # "research_paper" | "guideline" | "drug_profile" | "trial"
```

**Implementation notes**:
- Use `pypdf` for PDFs, `python-docx` for Word files, `BeautifulSoup` for HTML
- Preserve document structure (sections, headers) in metadata
- Assign stable doc_id (hash of source + title) for idempotency
- Skip documents already processed (check doc_id in database)

---

## Step 2: Text Chunking

**File**: `pipeline/ingestion/text_chunker.py`

**Strategy**: Parent Document Retrieval — two levels of chunks

```python
@dataclass
class ChunkPair:
    parent: TextChunk       # 800-1500 tokens — rich context for LLM
    children: list[TextChunk]  # 100-300 tokens — precise embedding matching

@dataclass
class TextChunk:
    chunk_id: str
    doc_id: str
    content: str
    token_count: int
    position: int           # sequence position in document
    parent_chunk_id: str | None  # None for parent chunks
    metadata: dict
```

**Rules**:
- Split on sentence boundaries, never mid-sentence
- Child chunks must map to exactly one parent
- Overlap between child chunks: 50 tokens (preserves context at boundaries)
- Preserve section headers in chunk metadata

---

## Step 3: Entity Extraction

**File**: `pipeline/extraction/entity_extractor.py`

**This is the most critical step — quality here determines graph quality.**

**Entity types for medical domain**:
```
Drug          → "Warfarin", "Aspirin", "Metformin"
Disease       → "Type 2 Diabetes", "Atrial Fibrillation", "CKD Stage 3"
Symptom       → "tachycardia", "elevated WBC", "shortness of breath"
Enzyme        → "CYP2C9", "CYP3A4", "P-glycoprotein"
Gene          → "VKORC1", "CYP2C19"
Protein       → "albumin", "creatinine"
Treatment     → "anticoagulation therapy", "dialysis"
Lab_Value     → "INR", "eGFR", "HbA1c"
Organism      → "Staphylococcus aureus", "SARS-CoV-2"
Clinical_Trial → "ARISTOTLE trial", "RELY trial"
Guideline     → "ACC/AHA AFib Guidelines 2023"
```

**Extraction prompt** (`pipeline/extraction/extraction_prompts.py`):
```python
ENTITY_EXTRACTION_PROMPT = """
You are a medical knowledge extraction expert.

Extract ALL entities from the medical text below.

For each entity output:
- name: exact canonical name (e.g., "Warfarin" not "warfarin" or "coumadin")
- type: one of [Drug, Disease, Symptom, Enzyme, Gene, Protein, Treatment, Lab_Value, Organism, Clinical_Trial, Guideline]
- description: one sentence describing this entity in medical context
- aliases: list of alternative names found in the text
- rxcui: RxNorm CUI if this is a drug (or null)
- icd10: ICD-10 code if this is a disease (or null)

Return JSON array of entities. Extract ALL entities, even if uncertain — mark uncertain ones with "confidence": "low".

Text:
{text}
"""
```

**Implementation**:
- Use GPT-4o for extraction (best structured output)
- Process in batches of 10 chunks
- Use retry with exponential backoff (circuit breaker)
- Validate output with Pydantic before storing
- Rate limit: 100 requests/minute to stay within API limits

---

## Step 4: Relationship Extraction

**File**: `pipeline/extraction/relationship_extractor.py`

**Relationship types**:
```
TREATS          → Drug TREATS Disease
CAUSES          → Drug CAUSES Symptom (side effect)
INTERACTS_WITH  → Drug INTERACTS_WITH Drug
METABOLIZED_BY  → Drug METABOLIZED_BY Enzyme
INHIBITS        → Drug INHIBITS Enzyme
INDUCES         → Drug INDUCES Enzyme
INDICATES       → Symptom INDICATES Disease
COMPLICATES     → Disease COMPLICATES Disease
CONTRAINDICATED → Drug CONTRAINDICATED_IN Disease/Condition
ALTERNATIVE_TO  → Drug ALTERNATIVE_TO Drug
USED_IN         → Drug USED_IN Clinical_Trial
PUBLISHED_IN    → Clinical_Trial PUBLISHED_IN guideline/paper
INCREASES_RISK  → Condition INCREASES_RISK_OF Condition
GENE_AFFECTS    → Gene AFFECTS Drug_Metabolism
```

**Relationship extraction prompt**:
```python
RELATIONSHIP_EXTRACTION_PROMPT = """
You are a medical relationship extraction expert.

Given the entities already extracted from this text, identify ALL relationships between them.

For each relationship output:
- source: entity name (must match an extracted entity)
- target: entity name (must match an extracted entity)
- relation: relationship type from the allowed list
- description: one sentence describing this specific relationship
- evidence: direct quote from text supporting this relationship
- confidence: 0.0-1.0
- direction: "directed" or "bidirectional"

Allowed relationship types:
TREATS | CAUSES | INTERACTS_WITH | METABOLIZED_BY | INHIBITS | INDUCES |
INDICATES | COMPLICATES | CONTRAINDICATED | ALTERNATIVE_TO | USED_IN |
PUBLISHED_IN | INCREASES_RISK | GENE_AFFECTS

Text: {text}
Extracted entities: {entities}
"""
```

---

## Step 5: Entity Resolution

**File**: `pipeline/resolution/entity_resolver.py`

**Problem**: "Warfarin", "warfarin sodium", "Coumadin", "warfarin (Coumadin)" are all the same entity. Without resolution, the graph has 4 disconnected nodes.

**Resolution strategy**:
1. **Exact match**: normalize to lowercase, strip special chars → exact key match
2. **Alias match**: check if name appears in `aliases` list of existing entity
3. **RxCUI match**: for drugs, match on RxNorm Concept Unique Identifier
4. **ICD-10 match**: for diseases, match on ICD-10 code
5. **Embedding similarity**: for remaining cases, embed entity name, find similar entities (threshold: 0.92 cosine similarity)
6. **Human review queue**: entities below threshold but above 0.85 → queue for human review

```python
class EntityResolver:
    async def resolve(self, entity: ExtractedEntity) -> str:
        """Returns canonical entity name to use (existing or new)"""

        # 1. Exact normalized match
        canonical = self._exact_match(entity.name)
        if canonical:
            return canonical

        # 2. Alias match
        canonical = await self._alias_match(entity.name, entity.aliases)
        if canonical:
            return canonical

        # 3. Code-based match
        if entity.rxcui:
            canonical = await self._rxcui_match(entity.rxcui)
            if canonical:
                return canonical

        # 4. Embedding similarity
        canonical = await self._embedding_match(entity.name, threshold=0.92)
        if canonical:
            return canonical

        # 5. This is a new entity — register it
        return entity.name
```

---

## Step 6: Graph Storage

**File**: `pipeline/graph_builder/graph_writer.py`

**Writes resolved entities and relationships to Neo4j**:
```python
WRITE_ENTITY_CYPHER = """
MERGE (e:Entity {name: $name})
SET e.type = $type,
    e.description = $description,
    e.aliases = $aliases,
    e.rxcui = $rxcui,
    e.icd10 = $icd10,
    e.updated_at = datetime()
"""

WRITE_RELATIONSHIP_CYPHER = """
MATCH (source:Entity {name: $source_name})
MATCH (target:Entity {name: $target_name})
MERGE (source)-[r:{relation_type}]->(target)
SET r.description = $description,
    r.evidence = $evidence,
    r.confidence = $confidence,
    r.source_doc = $source_doc,
    r.updated_at = datetime()
"""
```

**Important**: Use `MERGE` not `CREATE` — idempotent writes. Running twice produces same result.

---

## Step 7: Community Detection

**File**: `pipeline/community/community_detector.py`

**Uses Neo4j Graph Data Science Leiden algorithm**:
```python
LEIDEN_PROJECTION = """
CALL gds.graph.project(
    'medical_graph',
    'Entity',
    {
        INTERACTS_WITH: {orientation: 'UNDIRECTED'},
        TREATS: {orientation: 'UNDIRECTED'},
        CAUSES: {orientation: 'UNDIRECTED'},
        COMPLICATES: {orientation: 'UNDIRECTED'}
    }
)
"""

LEIDEN_RUN = """
CALL gds.leiden.write(
    'medical_graph',
    {
        writeProperty: 'community_level_{level}',
        maxLevels: 3,
        gamma: 1.0,
        theta: 0.01
    }
)
YIELD communityCount, modularity
"""
```

**Produces**: Each entity gets `community_level_0`, `community_level_1`, `community_level_2` property — its community assignment at each zoom level.

---

## Step 8: Community Summarization

**File**: `pipeline/community/community_summarizer.py`

**For each community at each level, generate an LLM summary**:
```python
COMMUNITY_SUMMARY_PROMPT = """
You are a medical knowledge summarizer.

Below are all entities and their relationships in a medical knowledge community.
Generate a comprehensive summary covering:
1. What this community is about (main medical topic)
2. Key entities and their roles
3. Important relationships and clinical implications
4. Any critical warnings or interactions present

Community entities and relationships:
{community_data}

Generate a 2-3 paragraph clinical summary that a doctor would find useful.
"""
```

**Output**: `CommunityReport` stored in vector store and linked to community ID in Neo4j.

---

## Step 9 & 10: Embedding + Indexing

**File**: `pipeline/embedding/embedding_writer.py`

**Three embedding targets**:
1. **Entity embeddings**: embed `entity.name + ": " + entity.description`
2. **Chunk embeddings**: embed child chunk content
3. **Community report embeddings**: embed community summary text

**Write to**:
- LanceDB: all embeddings with metadata
- Elasticsearch: chunk content for BM25 keyword index

```python
class EmbeddingWriter:
    async def embed_and_store(self, items: list[EmbeddableItem]) -> None:
        # Batch embed (BGE-M3 supports batch of 256)
        texts = [item.text for item in items]
        embeddings = await self._embedding_model.embed_batch(texts, batch_size=256)

        # Write to vector store
        records = [
            {"id": item.id, "text": item.text, "embedding": emb, "metadata": item.metadata}
            for item, emb in zip(items, embeddings)
        ]
        await self._vector_store.upsert(records)

        # Write to Elasticsearch for BM25
        for item in items:
            await self._search_engine.index_document(item.id, item.text, item.metadata)
```

---

## Pipeline Runner

**File**: `pipeline/pipeline_runner.py`

**Orchestrates all steps**:
```python
class PipelineRunner:
    async def run_full_pipeline(self, source_dirs: list[str]) -> PipelineResult:
        # Step 1-2: Ingest and chunk
        documents = await self.loader.load_all(source_dirs)
        chunks = await self.chunker.chunk_all(documents)

        # Step 3-4: Extract (in parallel batches)
        entities, relationships = await asyncio.gather(
            self.entity_extractor.extract_all(chunks),
            self.relationship_extractor.extract_all(chunks),
        )

        # Step 5: Resolve
        resolved = await self.entity_resolver.resolve_all(entities)

        # Step 6: Store in graph
        await self.graph_writer.write_all(resolved, relationships)

        # Step 7-8: Community detection + summarization
        await self.community_detector.run()
        await self.community_summarizer.summarize_all()

        # Step 9-10: Embed and index
        await self.embedding_writer.embed_and_index_all(chunks, resolved)

        return PipelineResult(
            documents_processed=len(documents),
            entities_created=len(resolved),
            relationships_created=len(relationships),
        )
```

---

## How to Run

```bash
# First time full pipeline
make ingest SOURCE=./data/medical_docs

# Daily update (new documents only)
make ingest-update SOURCE=./data/new_docs

# Check pipeline status
make pipeline-status
```

---

## Phase 1 Verification Checklist

Before moving to Phase 2, verify:
- [ ] Neo4j browser shows entities with correct types and properties
- [ ] Relationships between entities are correctly typed and directional
- [ ] Entity resolution correctly merges aliases (check "Warfarin" vs "Coumadin")
- [ ] Communities are assigned at all 3 levels
- [ ] Community summaries are generated and stored
- [ ] Vector store contains entity, chunk, and community embeddings
- [ ] Elasticsearch returns results for keyword searches
- [ ] Pipeline is idempotent — running twice produces same graph, no duplicates
