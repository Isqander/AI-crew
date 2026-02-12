FROM python:3.11-slim

WORKDIR /app

# Install root requirements (shared deps)
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Install gateway-specific requirements (PyJWT, bcrypt, email-validator)
COPY gateway/requirements.txt ./gateway/requirements.txt
RUN pip install --no-cache-dir -r gateway/requirements.txt

# Copy the full project (gateway imports config/, graphs/ for manifests)
COPY . .

EXPOSE 8081

CMD ["uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8081"]
