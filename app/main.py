from fastapi import FastAPI, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text, CursorResult, bindparam
from pydantic import BaseModel
from flashrank import Ranker
from .database import get_db
from flashrank import RerankRequest
from ollama import Client
import os
import json

os.environ['HTTPS_PROXY'] = ''
os.environ['HTTP_PROXY'] = ''
os.environ['https_proxy'] = ''
os.environ['http_proxy'] = ''

client = Client(
  host='http://localhost:11434',
  headers={'x-some-header': 'some-value'}
)

app = FastAPI()
rerank_model = Ranker(model_name="ms-marco-TinyBERT-L-2-v2", cache_dir="./.cache", max_length=2000)

class Search(BaseModel):
    vsm_query: str
    fts_query: str
    berlaku_only: bool
    tidak_berlaku_only: bool


@app.get("/")
def health_check():
    return {"Status": "Healthy"}

class Feedback(BaseModel):
    metadata: str

@app.post("/like")
def like(feedback: Feedback, db: Session = Depends(get_db)):
    db.execute(text("""
        INSERT INTO feedback_like (metadata) VALUES (:metadata)
    """), params={"metadata": feedback.metadata})
    db.commit()
    db.close()
    return {"status": "ok"}

@app.post("/dislike")
def dislike(feedback: Feedback, db: Session = Depends(get_db)):
    db.execute(text("""
        INSERT INTO feedback_dislike (metadata) VALUES (:metadata)
    """), params={"metadata": feedback.metadata})
    db.commit()
    db.close()
    return {"status": "ok"}

import time
def retrieval_generator(vsm_query: str, fts_query: str, berlaku_only: bool, tidak_berlaku_only: bool, db: Session):
    start = time.time()
    status_select = ""
    if berlaku_only:
        status_select = "Tidak Berlaku"
    elif tidak_berlaku_only:
        status_select = "Berlaku"
    else:
        status_select = "Semua"
    embedding_vector = client.embed(model="bge-m3", input=vsm_query).embeddings[0]
    yield "0;Selesai memahami query, sedang mencari informasi relevan...;null\n"
    print(f"embedding finsihed in {time.time() - start} seconds")
    start = time.time()
    res: CursorResult = db.execute(text("""
    SELECT chunk.page_number, chunk.legal_document_id,
    MAX((1 - (chunk.embedding <=> CAST(:query_embedding AS vector)))) AS similarity
    FROM legal_document_chunks AS chunk
    JOIN legal_documents AS doc ON doc.id = chunk.legal_document_id
    WHERE doc.status <> :status_select
    GROUP BY chunk.page_number, chunk.legal_document_id
    ORDER BY similarity DESC
    LIMIT 20;
    """), params={"query_embedding": embedding_vector, "status_select": status_select})
    data = []
    rows = res.fetchall()
    for i, row in enumerate(rows):
        data.append({
            "id": i + 1,
            "page_number": row[0],
            "doc_id": row[1]
        })
    yield f"1;Selesai menemukan informasi yang cocok, sedang mengurutkan relevansi informasi...;null\n"
    print(f"retrieval finsihed in {time.time() - start} seconds")
    selected_item = [(r["doc_id"], r["page_number"]) for r in data]
    yield f"2;Selesai mengumpulkan informasi, lanjut mencari tambahan informasi...;null\n"
    docs = []
    for id, page_number in selected_item:
        res = db.execute(text("""
            SELECT * FROM public.legal_document_page_metadata_view
            WHERE document_id = :id
            AND page_number BETWEEN :min_page AND :max_page
            AND status <> :status_select
        """), params={
            "id": id,
            "min_page": page_number - 2,
            "max_page": page_number + 2,
            "status_select": status_select
        })

        for doc in res:
            docs.append({
                "document_id": doc[0],
                "title": doc[1],
                "jenis_bentuk_peraturan": doc[2],
                "pemrakarsa": doc[3],
                "nomor": doc[4],
                "tahun": doc[5],
                "tentang": doc[6],
                "tempat_penetapan": doc[7],
                "ditetapkan_tanggal": doc[8],
                "pejabat_yang_menetapkan": doc[9],
                "status": doc[10],
                "url": doc[11],
                "dasar_hukum": doc[12],
                "mengubah": doc[13],
                "diubah_oleh": doc[14],
                "mencabut": doc[15],
                "dicabut_oleh": doc[16],
                "melaksanakan_amanat_peraturan": doc[17],
                "dilaksanakan_oleh_peraturan_pelaksana": doc[18],
                "page_number": doc[19],
                "combined_body": doc[20],
            })

    yield f"3;{len(docs)} informasi relevan berhasil dikumpulkan, sedang mencari dokumen yang informasi kata kunci;null\n"
    print(f"another retrieval finsihed in {time.time() - start} seconds")
    start = time.time()
    try:
        ts_lang = 'indonesian'
        stmt = text("""
            SELECT DISTINCT document_id, page_number, MAX(ts_rank_cd(full_text_search, to_tsquery(:lang, :ts_query))) AS rank
            FROM legal_document_pages
            WHERE full_text_search @@ to_tsquery(:lang, :ts_query) AND status <> :status_select
            GROUP BY document_id, page_number
            ORDER BY rank DESC
            LIMIT 20;
        """)
        print(f"fts done in {time.time() - start} seconds")


        res = db.execute(stmt, params={"lang": ts_lang, "ts_query": fts_query, "status_select": status_select})
        for id, page_number, _ in res:
            res = db.execute(text("""
                SELECT * FROM public.legal_document_page_metadata_view
                WHERE document_id = :id
                AND page_number BETWEEN :min_page AND :max_page
                AND status <> :status_select
            """), params={
                "id": id,
                "min_page": page_number - 2,
                "max_page": page_number + 2,
                "status_select": status_select
            })

            for doc in res:
                docs.append({
                    "document_id": doc[0],
                    "title": doc[1],
                    "jenis_bentuk_peraturan": doc[2],
                    "pemrakarsa": doc[3],
                    "nomor": doc[4],
                    "tahun": doc[5],
                    "tentang": doc[6],
                    "tempat_penetapan": doc[7],
                    "ditetapkan_tanggal": doc[8],
                    "pejabat_yang_menetapkan": doc[9],
                    "status": doc[10],
                    "url": doc[11],
                    "dasar_hukum": doc[12],
                    "mengubah": doc[13],
                    "diubah_oleh": doc[14],
                    "mencabut": doc[15],
                    "dicabut_oleh": doc[16],
                    "melaksanakan_amanat_peraturan": doc[17],
                    "dilaksanakan_oleh_peraturan_pelaksana": doc[18],
                    "page_number": doc[19],
                    "combined_body": doc[20],
                })
    except Exception as e:
        print(e)
    yield f"4;{len(docs)} informasi relevan berhasil dikumpulkan, mengurutkan informasi berdasarkan relevansi...;null\n"
    print(f"fts done in {time.time() - start} seconds")
    start = time.time()
    # deduplicate based on document_id
    payload = []
    ids = set()
    for doc in docs:
        if (doc["document_id"], doc["page_number"]) not in ids:
            payload.append(doc)
            ids.add((doc["document_id"], doc["page_number"]))

    rerank_request = RerankRequest(query=vsm_query, passages=[
        {
            "id": i,
            "text": doc["combined_body"],
            **doc
        } for i, doc in enumerate(payload)
    ])
    result = rerank_model.rerank(rerank_request)
    print(f"rerank done in {time.time() - start} seconds")
    yield f"done;Selesai mengumpulkan informasi, {len(docs)} informasi relevan ditemukan;{json.dumps(result, default=str)}\n"
    yield "data: done\n\n"
    db.close()

@app.post("/query")
def search(search: Search, db: Session = Depends(get_db)):
    return StreamingResponse(retrieval_generator(search.vsm_query, search.fts_query, search.berlaku_only, search.tidak_berlaku_only, db), media_type="text/event-stream")