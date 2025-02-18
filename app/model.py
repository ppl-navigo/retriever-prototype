from sentence_transformers import SentenceTransformer
from flashrank import Ranker, RerankRequest

embedding_model = SentenceTransformer("intfloat/multilingual-e5-large-instruct")
rerank_model = Ranker(model_name="ms-marco-TinyBERT-L-2-v2", cache_dir="./.cache", max_length=2000)