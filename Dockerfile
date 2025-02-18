# Use an official Python runtime as a parent image
FROM python:3.12

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app
RUN apt-get update && apt-get install
RUN apt-get install -y \
  dos2unix \
  libpq-dev \
  libmariadb-dev-compat \
  libmariadb-dev \
  gcc \
  && apt-get clean


# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
RUN python -c 'from sentence_transformers import SentenceTransformer; embedding_model = SentenceTransformer("intfloat/multilingual-e5-large-instruct")'
RUN python -c 'from flashrank import Ranker; rerank_model = Ranker(model_name="ms-marco-TinyBERT-L-2-v2", cache_dir="./.cache", max_length=2000)'
# Make port 80 available to the world outside this container
EXPOSE 80

# Run app.py when the container launches
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"]