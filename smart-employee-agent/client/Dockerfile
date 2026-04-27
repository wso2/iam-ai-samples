FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir python-dotenv

COPY . .

USER 10014

EXPOSE 3000

CMD ["python", "serve.py"]
