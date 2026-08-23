import time
import pytest
from fastapi.testclient import TestClient


def test_health_check(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_document_lifecycle_and_rag_query(client: TestClient):
    # 1. Upload a sample document with internal cross-references
    sample_text = (
        "Section 1. Payments.\n"
        "The buyer shall pay the seller $1,000 for the services.\n\n"
        "Section 2. Indemnity.\n"
        "Pursuant to Section 1, the seller shall indemnify the buyer against any liability arising from the services.\n"
    )
    
    files = {"file": ("test_agreement.txt", sample_text.encode("utf-8"), "text/plain")}
    upload_response = client.post("/documents/upload", files=files)
    
    assert upload_response.status_code == 201
    upload_data = upload_response.json()
    doc_id = upload_data["document_id"]
    assert doc_id.startswith("doc_")
    assert upload_data["status"] == "ready"
    assert upload_data["chunk_count"] > 0

    # 2. Get document metadata
    meta_response = client.get(f"/documents/{doc_id}")
    assert meta_response.status_code == 200
    meta_data = meta_response.json()
    assert meta_data["document_id"] == doc_id
    assert meta_data["filename"] == "test_agreement.txt"

    # 3. Query the document
    # We ask a question that triggers a cross-reference routing / multi-hop lookup.
    query_payload = {
        "question": "What are the indemnification obligations and how do they relate to payments?",
        "top_k": 3
    }
    
    # We give it a couple of seconds to ensure ChromaDB indexing is flushed (though ChromaDB is sync here)
    time.sleep(1)
    
    query_response = client.post(f"/documents/{doc_id}/query", json=query_payload)
    assert query_response.status_code == 200
    query_data = query_response.json()
    
    assert "answer" in query_data
    assert "citations" in query_data
    assert "answer_found" in query_data
    assert query_data["answer_found"] is True
    assert len(query_data["citations"]) > 0
    
    # Verify citations formatting: References section should be at the end of the answer
    assert "References:" in query_data["answer"]
    assert "[1]" in query_data["answer"]

    # 4. Query with a completely irrelevant question to test Stage 1 no-answer threshold filtering (score < 0.40)
    irrelevant_query = {
        "question": "What is the capital of France and what are its main tourist attractions?",
        "top_k": 3
    }
    irr_response = client.post(f"/documents/{doc_id}/query", json=irrelevant_query)
    assert irr_response.status_code == 200
    irr_data = irr_response.json()
    assert irr_data["answer_found"] is False
    assert len(irr_data["citations"]) == 0

    # 5. Delete the document
    delete_response = client.delete(f"/documents/{doc_id}")
    assert delete_response.status_code == 200
    
    # 6. Verify it is deleted
    get_after_delete = client.get(f"/documents/{doc_id}")
    assert get_after_delete.status_code == 404
