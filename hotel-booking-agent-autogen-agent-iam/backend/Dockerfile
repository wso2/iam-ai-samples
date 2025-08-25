FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install 'uvicorn[standard]'
RUN pip install poetry

# Clone and build asgardeo packages from GitHub
RUN git clone -b sdk https://github.com/shashimalcse/python.git /tmp/python-sdk

# Build and install asgardeo package
WORKDIR /tmp/python-sdk/packages/asgardeo
RUN poetry build
RUN pip install dist/*.whl

# Build and install asgardeo-ai package
WORKDIR /tmp/python-sdk/packages/asgardeo-ai
RUN poetry build
RUN pip install dist/*.whl

WORKDIR /app

COPY . .

# Install remaining requirements (excluding asgardeo packages)
RUN grep -v "asgardeo" requirements.txt > requirements_filtered.txt
RUN pip install -r requirements_filtered.txt

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]