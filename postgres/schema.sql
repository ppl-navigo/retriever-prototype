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

CREATE TABLE legal_document_chunks (
    id VARCHAR(32) PRIMARY KEY,
    body TEXT,
    filename TEXT,
    last_modified TIMESTAMP,
    page_number INT,
    embedding vector(1024),
    legal_document_id INT REFERENCES legal_documents(id) ON DELETE CASCADE
);

CREATE TABLE legal_document_elements (
    id UUID DEFAULT gen_random_uuid(),
    element_type VARCHAR(255),
    body TEXT,
    points JSONB,
    layout_width INT,
    layout_height INT,
    last_modified TIMESTAMP,
    page_number INT,
    legal_document_chunk_id VARCHAR(32) REFERENCES legal_document_chunks(id) ON DELETE CASCADE
);
