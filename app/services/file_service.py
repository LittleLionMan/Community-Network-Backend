import os
import io
import hashlib
import magic
from pathlib import Path
from typing import Tuple
from fastapi import HTTPException, UploadFile
from PIL import Image
import uuid

class FileUploadService:
    def __init__(self):
        self.upload_base = Path(os.getenv("UPLOAD_DIR", "/app/uploads")).absolute()
        self.profile_images_dir = self.upload_base / "profile_images"
        self.max_file_size = int(os.getenv("MAX_FILE_SIZE", "5242880"))  # 5MB default

        self.profile_images_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.profile_images_dir, 0o755)

        self.allowed_image_types = {
            'image/jpeg', 'image/png', 'image/gif', 'image/webp'
        }

        self.magic = magic.Magic(mime=True)

    async def upload_profile_image(self, file: UploadFile, user_id: int) -> Tuple[str, str]:
        if hasattr(file, 'size') and file.size and file.size > self.max_file_size:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size: {self.max_file_size // 1024 // 1024}MB"
            )

        content = await file.read()
        if len(content) > self.max_file_size:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size: {self.max_file_size // 1024 // 1024}MB"
            )

        detected_mime = self.magic.from_buffer(content)
        if detected_mime not in self.allowed_image_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed: {', '.join(self.allowed_image_types)}"
            )

        try:
            image = Image.open(io.BytesIO(content))
            image.verify()

            image = Image.open(io.BytesIO(content))
            if image.mode in ('RGBA', 'LA', 'P'):
                rgb_image = Image.new('RGB', image.size, (255, 255, 255))
                rgb_image.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                image = rgb_image

        except Exception:
            raise HTTPException(
                status_code=400,
                detail="Invalid or corrupted image file"
            )

        await self._scan_for_viruses(content)

        file_hash = hashlib.sha256(content).hexdigest()[:16]
        file_extension = self._get_safe_extension(detected_mime)
        filename = f"{user_id}_{uuid.uuid4().hex}_{file_hash}{file_extension}"

        file_path = self.profile_images_dir / filename

        await self._cleanup_old_profile_images(user_id)

        with open(file_path, 'wb') as f:
            image.save(f, format='JPEG', quality=85, optimize=True)

        os.chmod(file_path, 0o644)

        public_url = f"/uploads/profile_images/{filename}"
        return str(file_path), public_url

    async def _scan_for_viruses(self, content: bytes) -> None:
        suspicious_patterns = [
            b'<script',
            b'javascript:',
            b'<?php',
            b'<%',
            b'\x00',
        ]

        content_lower = content.lower()
        for pattern in suspicious_patterns:
            if pattern in content_lower:
                raise HTTPException(
                    status_code=400,
                    detail="File contains suspicious content"
                )

        # TODO: Integrate real virus scanner
        # try:
        #     result = clamd.scan_stream(content)
        #     if result and 'FOUND' in str(result):
        #         raise HTTPException(status_code=400, detail="Virus detected")
        # except Exception:
        #     # Fail safe - reject if scanner unavailable
        #     raise HTTPException(status_code=503, detail="Security scan unavailable")

    def _get_safe_extension(self, mime_type: str) -> str:
        """Map MIME types to safe extensions"""
        mime_to_ext = {
            'image/jpeg': '.jpg',
            'image/png': '.png',
            'image/gif': '.gif',
            'image/webp': '.webp'
        }
        return mime_to_ext.get(mime_type, '.jpg')

    async def _cleanup_old_profile_images(self, user_id: int) -> None:
        try:
            for file_path in self.profile_images_dir.glob(f"{user_id}_*"):
                if file_path.is_file():
                    file_path.unlink()
        except Exception as e:
            print(f"Failed to cleanup old images for user {user_id}: {e}")

    async def delete_profile_image(self, image_url: str) -> bool:
        try:
            if not image_url.startswith('/uploads/profile_images/'):
                return False

            filename = image_url.split('/')[-1]
            file_path = self.profile_images_dir / filename

            if not str(file_path.resolve()).startswith(str(self.profile_images_dir.resolve())):
                return False

            if file_path.exists():
                file_path.unlink()
                return True

        except Exception as e:
            print(f"Failed to delete image {image_url}: {e}")

        return False
