# 10 — Knowledge Graph Schema

## Neo4j Schema — Complete Entity and Relationship Design

---

## Entity (Node) Types

### Drug
```cypher
(:Drug {
    name: string,           // canonical: "Warfarin"
    rxcui: string,          // RxNorm CUI: "11289"
    drug_class: string,     // "anticoagulant"
    mechanism: string,      // "vitamin K antagonist"
    half_life: string,      // "20-60 hours"
    route: [string],        // ["oral"]
    aliases: [string],      // ["Coumadin", "warfarin sodium"]
    description: string,
    updated_at: datetime,
    community_level_0: int, // Leiden community at level 0
    community_level_1: int, // Leiden community at level 1
    community_level_2: int  // Leiden community at level 2
})
```

### Disease
```cypher
(:Disease {
    name: string,           // "Atrial Fibrillation"
    icd10: string,          // "I48"
    category: string,       // "cardiovascular"
    description: string,
    prevalence: string,
    aliases: [string],
    community_level_0: int,
    community_level_1: int,
    community_level_2: int
})
```

### Symptom
```cypher
(:Symptom {
    name: string,           // "tachycardia"
    description: string,
    measurement: string,    // "heart rate > 100 bpm"
    aliases: [string]
})
```

### Enzyme
```cypher
(:Enzyme {
    name: string,           // "CYP2C9"
    full_name: string,      // "Cytochrome P450 2C9"
    gene: string,           // "CYP2C9"
    location: string,       // "liver"
    function: string,
    aliases: [string]
})
```

### Gene
```cypher
(:Gene {
    name: string,           // "VKORC1"
    full_name: string,
    chromosome: string,
    function: string,
    clinical_significance: string
})
```

### Lab_Value
```cypher
(:Lab_Value {
    name: string,           // "INR"
    full_name: string,      // "International Normalized Ratio"
    normal_range: string,   // "0.8-1.2"
    therapeutic_range: string,  // "2.0-3.0 for anticoagulation"
    unit: string,           // "ratio"
    loinc: string           // "34714-6"
})
```

### Condition
```cypher
(:Condition {
    name: string,           // "CKD Stage 2"
    category: string,       // "renal"
    icd10: string,
    description: string
})
```

### Clinical_Trial
```cypher
(:Clinical_Trial {
    name: string,           // "ARISTOTLE trial"
    nct_id: string,         // "NCT00412984"
    phase: string,          // "Phase III"
    population: int,        // 18201
    primary_outcome: string,
    result_summary: string,
    publication_year: int
})
```

### Guideline
```cypher
(:Guideline {
    name: string,           // "ACC/AHA AFib Guidelines 2023"
    issuing_body: string,   // "American College of Cardiology"
    publication_year: int,
    url: string,
    recommendation_summary: string
})
```

### Community
```cypher
(:Community {
    community_id: string,   // "comm_0_142"
    level: int,             // 0, 1, or 2
    label: string,          // "Anticoagulants in Cardiac Patients"
    summary: string,        // LLM-generated summary
    entity_count: int,
    created_at: datetime
})
```

---

## Relationship (Edge) Types

### Drug → Disease
```cypher
(Drug)-[:TREATS {
    evidence_level: string,  // "A" | "B" | "C"
    indication: string,
    source_doc: string,
    confidence: float
}]->(Disease)

(Drug)-[:CONTRAINDICATED_IN {
    reason: string,
    severity: string,        // "absolute" | "relative"
    source_doc: string
}]->(Disease | Condition)
```

### Drug → Drug
```cypher
(Drug)-[:INTERACTS_WITH {
    severity: string,        // "major" | "moderate" | "minor"
    mechanism: string,
    clinical_effect: string, // "increased bleeding risk"
    management: string,      // "avoid combination" | "monitor INR"
    evidence: string,        // direct quote from literature
    confidence: float,
    source_doc: string
}]->(Drug)

(Drug)-[:ALTERNATIVE_TO {
    advantage: string,       // why this alternative is better
    patient_populations: [string],  // when to prefer this
    source_doc: string
}]->(Drug)
```

### Drug → Enzyme
```cypher
(Drug)-[:METABOLIZED_BY {
    fraction: float,         // 0.0-1.0 what fraction via this enzyme
    pathway: string,
    source_doc: string
}]->(Enzyme)

(Drug)-[:INHIBITS {
    type: string,            // "competitive" | "mechanism-based"
    ki: string,              // inhibition constant
    clinical_significance: string,
    source_doc: string
}]->(Enzyme)

(Drug)-[:INDUCES {
    fold_increase: string,
    time_to_effect: string,
    clinical_significance: string,
    source_doc: string
}]->(Enzyme)
```

### Disease / Condition → Disease / Condition
```cypher
(Disease)-[:COMPLICATES {
    mechanism: string,
    frequency: string,
    source_doc: string
}]->(Disease)

(Condition)-[:INCREASES_RISK_OF {
    risk_multiplier: float,
    mechanism: string,
    source_doc: string
}]->(Disease | Condition)
```

### Symptom → Disease
```cypher
(Symptom)-[:INDICATES {
    specificity: float,      // 0.0-1.0
    sensitivity: float,
    source_doc: string
}]->(Disease)
```

### Gene → Drug / Enzyme
```cypher
(Gene)-[:ENCODES {
    source_doc: string
}]->(Enzyme)

(Gene)-[:AFFECTS_METABOLISM_OF {
    variant: string,         // "CYP2C9*2", "CYP2C9*3"
    effect: string,          // "poor metabolizer"
    clinical_action: string,
    source_doc: string
}]->(Drug)
```

### Drug → Lab_Value
```cypher
(Drug)-[:MONITORED_BY {
    therapeutic_target: string,
    monitoring_frequency: string,
    source_doc: string
}]->(Lab_Value)

(Drug)-[:AFFECTS {
    direction: string,       // "increases" | "decreases"
    mechanism: string,
    source_doc: string
}]->(Lab_Value)
```

### Entity → Community
```cypher
(Entity)-[:MEMBER_OF {
    level: int
}]->(Community)
```

### Drug → Clinical_Trial
```cypher
(Drug)-[:STUDIED_IN {
    role: string,            // "intervention" | "comparator"
    outcome: string
}]->(Clinical_Trial)
```

---

## Constraints and Indexes

**File**: `migrations/graph/001_initial_schema.cypher`

```cypher
-- Uniqueness constraints
CREATE CONSTRAINT drug_name_unique IF NOT EXISTS
FOR (d:Drug) REQUIRE d.name IS UNIQUE;

CREATE CONSTRAINT disease_name_unique IF NOT EXISTS
FOR (d:Disease) REQUIRE d.name IS UNIQUE;

CREATE CONSTRAINT drug_rxcui_unique IF NOT EXISTS
FOR (d:Drug) REQUIRE d.rxcui IS UNIQUE;

CREATE CONSTRAINT disease_icd10_unique IF NOT EXISTS
FOR (d:Disease) REQUIRE d.icd10 IS UNIQUE;

CREATE CONSTRAINT community_id_unique IF NOT EXISTS
FOR (c:Community) REQUIRE c.community_id IS UNIQUE;

-- Performance indexes
CREATE INDEX entity_type_index IF NOT EXISTS
FOR (e:Entity) ON (e.type);

CREATE INDEX drug_class_index IF NOT EXISTS
FOR (d:Drug) ON (d.drug_class);

CREATE INDEX disease_category_index IF NOT EXISTS
FOR (d:Disease) ON (d.category);

CREATE INDEX community_level_index IF NOT EXISTS
FOR (c:Community) ON (c.level);

-- Full-text search index for entity names
CREATE FULLTEXT INDEX entity_name_fulltext IF NOT EXISTS
FOR (n:Drug|Disease|Symptom|Enzyme|Gene)
ON EACH [n.name, n.aliases];
```

---

## Example: Warfarin Subgraph

```
(Warfarin:Drug)
    │
    ├──[:TREATS]──────────────► (Atrial Fibrillation:Disease)
    ├──[:TREATS]──────────────► (DVT:Disease)
    ├──[:MONITORED_BY]────────► (INR:Lab_Value)
    │
    ├──[:METABOLIZED_BY]──────► (CYP2C9:Enzyme)
    │                                │
    │                         [:ENCODED_BY]
    │                                │
    │                           (CYP2C9:Gene)
    │                                │
    │                    [:AFFECTS_METABOLISM_OF]
    │                                └──────────► (Warfarin) [loop — genetic variant]
    │
    ├──[:INTERACTS_WITH {severity: "major"}]──► (Aspirin:Drug)
    │       "Increased bleeding risk: 3.2x baseline"
    │
    ├──[:INTERACTS_WITH {severity: "major"}]──► (NSAIDs:Drug)
    │
    ├──[:CONTRAINDICATED_IN]──► (Active Bleeding:Condition)
    ├──[:CONTRAINDICATED_IN]──► (Severe Renal Failure:Condition)
    │
    ├──[:ALTERNATIVE_TO {advantage: "safer in CKD"}]──► (Apixaban:Drug)
    │
    └──[:STUDIED_IN]──────────► (RE-LY Trial:Clinical_Trial)
                                (ARISTOTLE Trial:Clinical_Trial)
```

---

## Key Cypher Queries Used by Agents

### Find drug interactions (used by local_graph_search)
```cypher
MATCH (d1:Drug {name: $drug_name})-[r:INTERACTS_WITH]-(d2:Drug)
WHERE r.severity IN ['major', 'moderate']
RETURN d1.name, d2.name, r.severity, r.clinical_effect, r.management
ORDER BY r.severity
```

### Multi-hop risk chain (used for complex reasoning)
```cypher
MATCH path = (drug:Drug {name: $drug_name})-[:METABOLIZED_BY]->(enzyme:Enzyme)
             <-[:INHIBITS]-(inhibitor:Drug)
WHERE inhibitor.name IN $patient_current_drugs
RETURN drug.name, enzyme.name, inhibitor.name,
       "Inhibited metabolism — drug levels may increase" as risk
```

### Find all contraindications for patient profile
```cypher
MATCH (drug:Drug {name: $new_drug})-[:CONTRAINDICATED_IN]->(condition)
WHERE condition.name IN $patient_conditions
RETURN drug.name, condition.name, "contraindicated" as status

UNION

MATCH (drug:Drug {name: $new_drug})-[r:INTERACTS_WITH]-(existing:Drug)
WHERE existing.name IN $patient_medications
AND r.severity = 'major'
RETURN drug.name, existing.name, r.clinical_effect as status
```

### Community context for synthesis
```cypher
MATCH (e:Entity {name: $entity_name})-[:MEMBER_OF {level: $level}]->(c:Community)
RETURN c.community_id, c.label, c.summary
```
