"""Private S3-compatible object storage. Keys never contain user-supplied names."""
import uuid

import boto3
from botocore.config import Config

from .config import settings

s3 = boto3.client(
    "s3",
    endpoint_url=settings.AWS_ENDPOINT_URL_S3,
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    region_name=settings.AWS_REGION,
    config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
)


def put(user_id: str, ext: str, data: bytes, ctype: str) -> str:
    key = f"{user_id}/{uuid.uuid4()}.{ext}"
    s3.put_object(Bucket=settings.BUCKET, Key=key, Body=data, ContentType=ctype)
    return key


def get(key: str) -> bytes:
    return s3.get_object(Bucket=settings.BUCKET, Key=key)["Body"].read()


def delete(key: str) -> None:
    s3.delete_object(Bucket=settings.BUCKET, Key=key)
