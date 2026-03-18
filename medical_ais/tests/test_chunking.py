"""Unit tests for the document chunking module."""
from __future__ import annotations

import pytest

from medical_ais.pipeline.chunking import chunk_document
from medical_ais.pipeline.ingestion import RawDocument


def make_doc(text: str = None) -> RawDocument:
    t = text or (
        "Metformin is the first-line treatment for type 2 diabetes. "
        "It works by reducing hepatic glucose production and improving insulin sensitivity. "
        "Common side effects include nausea and diarrhoea. "
        "It is generally well tolerated and inexpensive. "
        "Rare but serious side effects include lactic acidosis. "
        "It should not be used in patients with severe renal impairment. "
        "Patients with eGFR < 30 should discontinue metformin."
    ) * 5
    return RawDocument(id="test_doc", source_path="test.txt", text=t)


def test_chunk_produces_parents_and_children():
    doc = make_doc()
    parents, children = chunk_document(doc, parent_chunk_size=300, child_chunk_size=100)
    assert len(parents) > 0
    assert len(children) > 0
    assert len(children) >= len(parents)


def test_all_children_have_parent_id():
    doc = make_doc()
    _, children = chunk_document(doc)
    for child in children:
        assert child.parent_id is not None
        assert child.chunk_type == "child"


def test_all_parents_have_no_parent_id():
    doc = make_doc()
    parents, _ = chunk_document(doc)
    for parent in parents:
        assert parent.parent_id is None
        assert parent.chunk_type == "parent"


def test_chunk_ids_are_unique():
    doc = make_doc()
    parents, children = chunk_document(doc)
    all_ids = [c.id for c in parents + children]
    assert len(all_ids) == len(set(all_ids))
