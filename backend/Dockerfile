FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y git \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*


RUN python -c "import clip; clip.load('ViT-B/32', device='cpu')"

COPY . .

EXPOSE 8000

ENV OMP_NUM_THREADS=4
ENV MKL_NUM_THREADS=4

CMD ["sh", "-c", "until alembic upgrade head; do echo 'Waiting for database...'; sleep 2; done && uvicorn main:app --host 0.0.0.0 --port 8000"]
