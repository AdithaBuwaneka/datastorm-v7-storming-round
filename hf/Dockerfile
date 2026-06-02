# Hugging Face Spaces container for the DataX backend.
# The Space repo is assembled by .github/workflows/deploy-backend-to-hf.yml:
# every push to main on GitHub stages this Dockerfile alongside the backend
# code + gold data files at the Space repo root, then force-pushes the
# bundle to https://huggingface.co/spaces/adithaf7/datax-outlet-intelligence-api
FROM python:3.11-slim

# Avoid prompts and shrink image
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /code

# Hugging Face runs containers as a non-root user with uid 1000. Pre-create
# the user so file ownership is predictable.
RUN useradd -m -u 1000 user

# Install system deps for pyarrow / pandas wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Python deps first, so changes to data don't bust the dep cache
COPY --chown=user:user requirements.txt /code/requirements.txt
RUN pip install --upgrade pip && pip install -r /code/requirements.txt

# Application code + data files. The GitHub Actions workflow stages these
# from webapp/backend/ + data/gold/ + outputs/ in the source repo.
COPY --chown=user:user . /code/

USER user

# Hugging Face Spaces requires the app to listen on the value of $PORT
# (defaults to 7860). REPO_ROOT lets the data_loader find /code instead
# of walking up.
ENV PORT=7860 \
    REPO_ROOT=/code

EXPOSE 7860

CMD ["sh", "-c", "python -m uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
