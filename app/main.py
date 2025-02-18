from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text, CursorResult
from pydantic import BaseModel
from .model import embedding_model, rerank_model
from .database import get_db
from dotenv import load_dotenv
from flashrank import RerankRequest

app = FastAPI()

class Search(BaseModel):
    query: str
    history: list[str]

@app.get("/")
def health_check():
    return {"Status": "Healthy"}

@app.post("/query")
def search(search: Search, db: Session = Depends(get_db)):
    query = f"""
    Anda adalah sebuah search engine undang-undang yang menerima query berikut:
    === BEGIN QUERY ===
    {search.query}
    === END QUERY ===
    {"Selain itu, Anda juga menerima history query berikut:\n" + "\n".join(search.history) if search.history else ""}
    Carilah dokumen yang paling relevan dengan query tersebut.
    """

    embedding_vector = embedding_model.encode(query)
    res: CursorResult = db.execute(text("""--sql
        SELECT chunk.body, chunk.page_number, chunk.last_modified,
        doc.title, doc.jenis_bentuk_peraturan, doc.pemrakarsa,
        doc.nomor, doc.tahun, doc.tentang, doc.tempat_penetapan,
        doc.ditetapkan_tanggal, doc.pejabat_yang_menetapkan, doc.url,
        1 - (chunk.embedding <=> CAST(:query_embedding AS vector)) as similarity,
        doc.id, doc.status, chunk.id
        FROM legal_document_chunks AS chunk
        JOIN legal_documents AS doc ON doc.id = chunk.legal_document_id
        -- WHERE CAST(:query_embedding AS vector) <=> chunk.embedding > 0.7
        ORDER BY similarity DESC
        LIMIT 100;
    """), params={"query_embedding": embedding_vector.tolist()})

    data = []
    rows = res.fetchall()
    for i, row in enumerate(rows):
        data.append({
            "id": i+1,
            "text": row[0],
            "page_number": row[1],
            "doc_title": row[3],
            "source": row[12],
            "similiarity": row[13],
            "metadata": {
                "doc_id": row[14],
                "last_modified": row[2],
                "type": row[4],
                "initiator": row[5],
                "number": row[6],
                "year": row[7],
                "about": row[8],
                "place_of_establisment": row[9],
                "date_of_establishment": row[10],
                "official_of_establishment": row[11],
                "status": row[15],
                "chunk_id": row[16],
            },
        })

    print(data)

    rerank_request = RerankRequest(query=query, passages=data)
    if len(data) == 0:
        return []

    result = rerank_model.rerank(rerank_request)[:20]
    for i, r in enumerate(result):
        r["id"] = i+1
        r["score"] = r["score"].item()
    
    return result