// ─────────────────────────────────────────────────────────────────────────────
// Neo4j Schema Migration 001 — Medical Knowledge Graph
// Run with: cypher-shell -u neo4j -p <password> -f 001_graph_schema.cypher
// ─────────────────────────────────────────────────────────────────────────────

// ── Uniqueness constraints ────────────────────────────────────────────────────
CREATE CONSTRAINT entity_unique_name IF NOT EXISTS
  FOR (e:Entity) REQUIRE e.canonical_name IS UNIQUE;

CREATE CONSTRAINT drug_unique_name IF NOT EXISTS
  FOR (d:Drug) REQUIRE d.canonical_name IS UNIQUE;

CREATE CONSTRAINT disease_unique_name IF NOT EXISTS
  FOR (d:Disease) REQUIRE d.canonical_name IS UNIQUE;

// ── Indexes for fast lookup ───────────────────────────────────────────────────
CREATE INDEX entity_type_idx IF NOT EXISTS
  FOR (e:Entity) ON (e.entity_type);

CREATE INDEX entity_community_idx IF NOT EXISTS
  FOR (e:Entity) ON (e.community_id);

// Full-text index for fuzzy entity search
CALL db.index.fulltext.createNodeIndex(
  "entity_fulltext",
  ["Entity"],
  ["canonical_name", "description"],
  {analyzer: "english"}
) IF NOT EXISTS;

// ── Sample Drug nodes (seed data for testing) ─────────────────────────────────
MERGE (m:Entity:Drug {canonical_name: "Metformin"})
SET m.entity_type = "Drug",
    m.description = "First-line oral antidiabetic drug; biguanide class",
    m.aliases = ["metformin hydrochloride", "Glucophage"];

MERGE (w:Entity:Drug {canonical_name: "Warfarin"})
SET w.entity_type = "Drug",
    w.description = "Anticoagulant; vitamin K antagonist",
    w.aliases = ["Coumadin", "warfarin sodium"];

MERGE (d:Entity:Disease {canonical_name: "Type 2 Diabetes"})
SET d.entity_type = "Disease",
    d.description = "Metabolic disorder characterised by insulin resistance",
    d.aliases = ["T2DM", "diabetes mellitus type 2"];

MERGE (a:Entity:Disease {canonical_name: "Atrial Fibrillation"})
SET a.entity_type = "Disease",
    a.description = "Irregular heart rhythm; increases stroke risk",
    a.aliases = ["AF", "AFib"];

MERGE (e:Entity:Enzyme {canonical_name: "CYP2C9"})
SET e.entity_type = "Enzyme",
    e.description = "Cytochrome P450 enzyme involved in drug metabolism";

// ── Sample relationships ───────────────────────────────────────────────────────
MATCH (m:Entity {canonical_name: "Metformin"}),
      (d:Entity {canonical_name: "Type 2 Diabetes"})
MERGE (m)-[r:RELATIONSHIP {type: "TREATS"}]->(d)
SET r.confidence = 1.0, r.evidence = "WHO Essential Medicines List";

MATCH (w:Entity {canonical_name: "Warfarin"}),
      (e:Entity {canonical_name: "CYP2C9"})
MERGE (w)-[r:RELATIONSHIP {type: "METABOLIZED_BY"}]->(e)
SET r.confidence = 0.98, r.evidence = "Warfarin is primarily metabolized by CYP2C9";

MATCH (w:Entity {canonical_name: "Warfarin"}),
      (a:Entity {canonical_name: "Atrial Fibrillation"})
MERGE (w)-[r:RELATIONSHIP {type: "TREATS"}]->(a)
SET r.confidence = 0.95, r.evidence = "Standard anticoagulation for AF stroke prevention";
