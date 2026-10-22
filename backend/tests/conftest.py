import os

for k, v in {
    "DATABASE_URL": "postgresql://u:p@localhost/db", "NEON_AUTH_BASE_URL": "https://auth.test/x",
    "NEON_AUTH_JWKS_URL": "https://auth.test/jwks", "AWS_ACCESS_KEY_ID": "k", "AWS_SECRET_ACCESS_KEY": "s",
    "AWS_ENDPOINT_URL_S3": "https://s3.test", "NVIDIA_API_KEY": "nvapi-test", "NVIDIA_MODEL": "test-model",
    "LLM_BACKOFF_S": "0", "ENV": "dev",
}.items():
    os.environ.setdefault(k, v)
