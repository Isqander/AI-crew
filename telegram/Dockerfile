FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source files into a proper Python package directory.
# Build context is ./telegram, so COPY . . would place files at /app/
# (flat), but `python -m telegram.bot` requires /app/telegram/ package.
COPY . ./telegram/

CMD ["python", "-m", "telegram.bot"]
