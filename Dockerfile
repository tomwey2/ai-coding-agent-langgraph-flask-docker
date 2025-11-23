FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# 1. System-Pakete installieren
# Wir brauchen NUR NOCH git (das Tool selbst)
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# 2. 'uv' installieren
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
