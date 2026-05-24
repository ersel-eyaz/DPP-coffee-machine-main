# backend/Dockerfile
FROM python:3.12.3-bookworm

# Minimal OS
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# PDM env
ENV PDM_CHECK_UPDATE=false \
    PDM_USE_VENV=true \
    PDM_VENV_IN_PROJECT=1

# Install PDM
RUN curl -sSL https://pdm-project.org/install-pdm.py | python3 -

WORKDIR /project

# Copy only files that affect legacy backend deps first
COPY pyproject.toml README.md ./
# Preserve the legacy optional-lock behavior.
RUN if [ -f pdm.lock ]; then cp pdm.lock .; fi

# Create the venv explicitly and put it first on PATH
RUN python -m venv /project/.venv
ENV VIRTUAL_ENV=/project/.venv
ENV PATH="/project/.venv/bin:/root/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

# Install production deps into the venv
RUN pdm use -f /project/.venv && pdm install --prod --no-editable

# Install data-quality semantic runtime separately from legacy backend deps.
COPY data-quality-requirements.txt ./
# Semantic harmonization runs on CPU; avoid pulling CUDA runtime packages into the local demo image.
RUN pip install --no-cache-dir torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r data-quality-requirements.txt

# tiny entrypoint that can re-install if venv is missing
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# app code last for faster rebuilds
COPY src/ /project/src
ENV PYTHONPATH="/project/src"

EXPOSE 8000

# Run the app with Uvicorn
ENTRYPOINT ["/entrypoint.sh"]
CMD ["pdm", "run", "uvicorn", "dpp.server:app", "--host", "0.0.0.0", "--port", "8000"]
