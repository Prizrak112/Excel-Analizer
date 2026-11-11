import os
import shutil
import base64
import hashlib
from pathlib import Path
from cryptography.fernet import Fernet

def get_key(password: str) -> bytes:
    digest = hashlib.sha256(password.encode('utf-8')).digest()
    return base64.urlsafe_b64encode(digest)

def build_encrypted_project(password: str, source_dirs: list, output_dir: str = "build"):
    key = get_key(password)
    cipher = Fernet(key)
    
    # 1. Очищаем папку сборки, если она была
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)
    
    # 2. Создаем структуру внутри build
    build_src_dir = Path(output_dir) / "src"
    os.makedirs(build_src_dir)
    
    for d in source_dirs:
        src_dir = Path(d)
        if not src_dir.exists():
            continue
        
        # Копируем папки ui и core в build/src/
        dest_dir = build_src_dir / src_dir.name
        shutil.copytree(src_dir, dest_dir)
        
        # 3. Шифруем файлы ТОЛЬКО внутри папки сборки
        for root, _, files in os.walk(dest_dir):
            for file in files:
                if file.endswith(".py") and file not in ("__init__.py",):
                    path = Path(root) / file
                    
                    with open(path, "rb") as f:
                        data = f.read()
                    
                    encrypted = cipher.encrypt(data)
                    enc_path = path.with_suffix(".enc")
                    
                    with open(enc_path, "wb") as f:
                        f.write(encrypted)
                    
                    # Удаляем .py файл ТОЛЬКО в папке сборки
                    os.remove(path)
                    
    print(f"\n✅ Сборка завершена!")
    print(f"Защищенная версия проекта лежит в папке: '{output_dir}'.")
    print(f"Твои оригинальные исходники в папке 'src' остались нетронутыми.")

if __name__ == "__main__":
    pwd = input("Введите мастер-пароль для шифрования ядра NexGrid: ")
    # Указываем, какие папки берем для шифрования
    build_encrypted_project(pwd, ["src/ui", "src/core"])