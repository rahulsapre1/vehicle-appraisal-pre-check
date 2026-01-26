FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY apps/mcp/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY apps/mcp/ /app/

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV API_BASE_URL=http://api:8000

# MCP server uses stdio transport (stdin/stdout)
# No port exposure needed
CMD ["python", "server.py"]
