# Prototype Retrieval Pipeline Navigo

## Pendahuluan
Aplikasi ini adalah sistem pencarian dokumen hukum yang dibangun menggunakan FastAPI. Sistem ini dirancang untuk mempermudah pencarian dokumen hukum berdasarkan relevansi dengan menggunakan kombinasi pencarian berbasis vektor (embedding-based retrieval), pencarian teks penuh (Full-Text Search/FTS), serta peringkat ulang (reranking) agar hasil lebih akurat dan relevan.

## Schema Database
Berikut adalah schema database terbaru
```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE legal_documents (
    id SERIAL PRIMARY KEY,
    title TEXT,
    jenis_bentuk_peraturan TEXT,
    pemrakarsa TEXT,
    nomor TEXT,
    tahun INT,
    tentang TEXT,
    tempat_penetapan TEXT,
    ditetapkan_tanggal DATE,
    pejabat_yang_menetapkan TEXT,
    status TEXT,
    url TEXT,

    tahun_pengundangan INT,
    tanggal_pengundangan DATE,
    nomor_pengundangan INT,
    nomor_tambahan INT,
    pejabat_pengundangan TEXT,

    dasar_hukum JSONB,
    mengubah JSONB,
    diubah_oleh JSONB,
    mencabut JSONB,
    dicabut_oleh JSONB,
    melaksanakan_amanat_peraturan JSONB,
    dilaksanakan_oleh_peraturan_pelaksana JSONB,

    filenames JSONB,
    resource_urls JSONB,
    reference_urls JSONB,

    content_type JSONB,
    content_text JSONB
);

CREATE TABLE legal_document_chunks ( -- untuk vector semantic search
    id VARCHAR(32) PRIMARY KEY,
    body TEXT,
    filename TEXT,
    last_modified TIMESTAMP,
    page_number INT,
    embedding vector(1024),
    legal_document_id INT REFERENCES legal_documents(id) ON DELETE CASCADE
);

CREATE TABLE legal_document_pages ( -- untukl full text search
    id SERIAL PRIMARY KEY,
    document_id VARCHAR(255) NOT NULL,
    page_number INTEGER,
    title TEXT,
    jenis_bentuk_peraturan TEXT,
    pemrakarsa TEXT,
    nomor TEXT,
    tahun INTEGER,
    tentang TEXT,
    tempat_penetapan TEXT,
    ditetapkan_tanggal DATE,
    pejabat_yang_menetapkan TEXT,
    status TEXT,
    url TEXT,
    dasar_hukum TEXT,
    mengubah TEXT,
    diubah_oleh TEXT,
    mencabut TEXT,
    dicabut_oleh TEXT,
    melaksanakan_amanat_peraturan TEXT,
    dilaksanakan_oleh_peraturan_pelaksana TEXT,
    combined_body TEXT,
    full_text_search TSVECTOR,
    FOREIGN KEY (document_id) REFERENCES legal_documents(id) ON DELETE CASCADE,
    UNIQUE (document_id, page_number)
);
```

## Instalasi
### Persyaratan
- Python 3.8+
- FastAPI
- SQLAlchemy
- Pydantic
- Flashrank
- Ollama Client
- PostgreSQL (dengan ekstensi vektor untuk pencarian berbasis embedding)

### Langkah-langkah Instalasi
1. Clone repositori ini:
   ```sh
   git clone <repo-url>
   cd <repo-folder>
   ```
2. Instal dependensi yang diperlukan:
   ```sh
   pip install -r requirements.txt
   ```
3. Atur variabel lingkungan untuk menghapus pengaturan proxy (jika diperlukan):
   ```sh
   export HTTPS_PROXY=""
   export HTTP_PROXY=""
   export https_proxy=""
   export http_proxy=""
   ```
4. Jalankan aplikasi dengan perintah:
   ```sh
   uvicorn main:app --reload
   ```

## API Endpoint
### 1. Pemeriksaan Kesehatan Server
**GET /**
- Mengecek apakah server berjalan dengan baik.
- Response:
  ```json
  {"Status": "Healthy"}
  ```

### 2. Pencarian Dokumen Hukum
**POST /query**
- Memproses pencarian berdasarkan query pengguna.
- Body berasal dari hasil prompting ke LLM, teknik ini dikenal sebagai teknik metaprompting
- Metaprompting mengubah query seperti "apa saja kewenangan seorang notaris?" menjadi "wewenang notaris"
- Metaprompting mengubah query dengan bahasa manusia menjadi query yang lebih ramah terhadap sistem retrieval
- Contoh permintaan JSON:
  ```json
  {
    "vsm_query": "pertanyaan tentang regulasi pajak",
    "fts_query": "pajak perusahaan",
    "berlaku_only": true,
    "tidak_berlaku_only": false
  }
  ```
- Mengembalikan hasil secara streaming dengan pembaruan bertahap.

### 3. Sistem Feedback
**POST /like**
- Menyimpan feedback jika pengguna menyukai hasil pencarian.
  ```json
  {
    "metadata": "id dokumen yang disukai"
  }
  ```

**POST /dislike**
- Menyimpan feedback jika pengguna tidak menyukai hasil pencarian.
  ```json
  {
    "metadata": "id dokumen yang tidak disukai"
  }
  ```

## Alur Pemrosesan Query
1. **Ekstraksi Embedding dari Query** – Query yang diberikan oleh pengguna dikonversi menjadi vektor embedding menggunakan `Ollama`. 
   - **Alasan**: Langsung menggunakan ```sentence-transformers``` cenderung tidak stabil dan membuat image docker menjadi sangat berat, sehingga di server langsung ditambahkan server Ollama.

2. **Pencarian Berdasarkan Embedding Vektor** – Sistem mencari dokumen yang memiliki kemiripan tertinggi dengan embedding query pengguna menggunakan PostgreSQL dengan ekstensi vektor.
```python
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
```
   - **Alasan**: Pendekatan ini memungkinkan pencarian dokumen meskipun pengguna tidak menggunakan kata yang persis sama dengan dokumen. Kelemahanya adalah context size yang terbatas, sehingga harus di chunk menjadi bagian-bagian kecil.

3. **Pencarian Teks Penuh (FTS)** – Sistem juga melakukan pencarian berbasis teks penuh untuk menemukan dokumen yang secara eksplisit menyebutkan kata kunci yang dicari.
```python
    stmt = text("""
    SELECT DISTINCT document_id, page_number, MAX(ts_rank_cd(full_text_search, to_tsquery(:lang, :ts_query))) AS rank
    FROM legal_document_pages
    WHERE full_text_search @@ to_tsquery(:lang, :ts_query) AND status <> :status_select
    GROUP BY document_id, page_number
    ORDER BY rank DESC
    LIMIT 20;
        """)
```
   - **Alasan**: FTS memberikan hasil pencarian yang lebih presisi dalam konteks tertentu dibandingkan pendekatan embedding. FTS dapat melakukan retrieval dengan dokumen yang lebih panjang dari batas konteks dari vector search.

4. **Pengambilan Data Dokumen** – Setelah hasil pencarian diperoleh, metadata dari dokumen yang relevan dikumpulkan untuk ditampilkan kepada pengguna.
```python
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
```
Dari dokumen yang diambil, lakukan ekstraksi pada satu halaman, dan dua halaman diantaranya, misalnya halaman ke-3 cocok dengan query, maka halaman 1-5 juga akan diambil
Ini untuk mencegah konteks terpotong ketika retrieval

5. **Peringkat Ulang (Reranking)** – Hasil pencarian disusun ulang menggunakan `flashrank` agar urutan hasil lebih sesuai dengan relevansi.
```python
rerank_request = RerankRequest(query=vsm_query, passages=[
    {
        "id": i,
        "text": doc["combined_body"],
        **doc
    } for i, doc in enumerate(payload)
])
result = rerank_model.rerank(rerank_request)
```
Reranking mengurutkan dokumen dari yang paling relevan hingga paling tidak relevan terhadap query pengguna
   - **Alasan**: Model reranking dapat meningkatkan kualitas hasil pencarian dengan mempertimbangkan konteks lebih dalam dibandingkan sekadar skor pencocokan vektor atau teks.

6. **Streaming Hasil ke Klien** – Hasil dikirimkan secara bertahap agar pengguna mendapatkan informasi secepat mungkin tanpa harus menunggu seluruh proses selesai.
```python
@app.post("/query")
def search(search: Search, db: Session = Depends(get_db)):
    return StreamingResponse(retrieval_generator(search.vsm_query, search.fts_query, search.berlaku_only, search.tidak_berlaku_only, db), media_type="text/event-stream")
```
   - **Alasan**: Mengurangi waktu tunggu pengguna dan meningkatkan pengalaman interaktif.

## Dependensi
- `FastAPI` – Framework untuk membangun API yang cepat dan ringan.
- `SQLAlchemy` – ORM untuk mengelola basis data secara efisien.
- `Flashrank` – Sistem peringkat ulang untuk meningkatkan akurasi hasil pencarian.
- `Ollama` – Layanan untuk menghasilkan embedding dari query pengguna.
- `PostgreSQL` – Basis data utama dengan dukungan vektor untuk pencarian embedding.

## Cara Deployment
Untuk menjalankan aplikasi dalam lingkungan produksi, gunakan perintah berikut:
```sh
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

## Overall Progress
### Isu Sebelumnya
- konteks yang diberikan ke LLM sangat pendek sehingga banyak informasi yang terpotong dan tidak disajikan
- dokumen yang diambil kurang relevan dan bahkan tidak mengandung kata kunci
- Jumlah konteks yang diberikan ke LLM sangat sedikit

### Solusi
- Menggabungkan kemampuan search dari embedding model dengan full text search menggunakan fitur tsvector postgres
- Seluruh chunk dan bagian lain yang di ekstrasi, dilakukan penggabungan untuk mengambil seluruh halaman pada dokumen tersebut beserta 2 halaman sebelum dan sesudah dari halaman tersebut.
- Melakukan reranking di akhir

### Masalah Selanjutnya
- Kecepatan query sangat lambat
- Perlu menimbang metode optimisasi