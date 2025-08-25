# Use an official Python runtime as a base image
FROM python:3.11-alpine3.22.1

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apk add --no-cache \
    build-base \
    postgresql-dev \
    git \
    gcc \
    musl-dev \
    libffi-dev

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip

WORKDIR /app

RUN addgroup -g 10014 choreo && \
    adduser  --disabled-password  --no-create-home --uid 10014 --ingroup choreo choreouser


# Install remaining requirements
RUN pip install -r requirements.txt

# Copy project files
COPY . .

# Switch to the new user
USER 10014

# Expose port (change if needed)
EXPOSE 8000

# Run the application (adjust as needed)
CMD ["uvicorn", "app.service:app", "--host", "0.0.0.0", "--port", "8002"]

 
