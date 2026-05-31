FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    unzip \
    tor \
    && curl -fsSL https://deno.land/install.sh | sh \
    && echo 'export DENO_INSTALL="/root/.deno"' >> /root/.bashrc \
    && echo 'export PATH="$DENO_INSTALL/bin:$PATH"' >> /root/.bashrc \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.deno/bin:${PATH}"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x start.sh
CMD ["bash", "start.sh"]
