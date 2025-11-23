# Basis Image
FROM python:3.11-slim-bookworm

# Umgebungsvariablen
ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# 1. System-Pakete installieren
# git (für Agent), nodejs/npm (für MCP Server), curl (für Tools)
RUN apt-get update && apt-get install -y \
    git \
    nodejs \
    npm \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 2. 'uv' installieren
# WIR NUTZEN PIP: Das ist im Python-Container der stabilste Weg.
# Kein "failed to fetch oauth token" mehr.
RUN pip install uv

# 3. Dependencies installieren
COPY pyproject.toml uv.lock ./

# Installiere Abhängigkeiten ins System-Python
RUN uv sync --frozen --no-install-project

# 4. Code kopieren
COPY . .

# 5. Git Dummy-Config (damit der Agent committen kann)
RUN git config --global user.email "agent@bot.local" && \
    git config --global user.name "AI Coding Agent"

# 6. Startbefehl
CMD ["uv", "run", "main.py"]
