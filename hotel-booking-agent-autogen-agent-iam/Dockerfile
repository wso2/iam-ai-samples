# Use an official Python runtime as a base image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt
RUN pip install 'uvicorn[standard]'

# Copy project files
COPY . .

USER 10014

# Expose port (change if needed)
EXPOSE 8000

# Run the application (adjust as needed)
CMD ["uvicorn", "app.service:app", "--host", "0.0.0.0", "--port", "8000"]

 
