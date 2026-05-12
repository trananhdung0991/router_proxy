FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir flask flask-cors

# Copy license server
COPY license_server.py /app/

# Create data directory
RUN mkdir -p /app/data && \
    chmod 755 /app/data

# Expose port
EXPOSE 10001

# Set environment variables
ENV ADMIN_TOKEN=change-me-please
ENV DATABASE=/app/data/licenses.db

# Run server
CMD ["python3", "license_server.py"]
