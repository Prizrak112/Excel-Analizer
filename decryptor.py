import os
import base64
import hashlib
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken

def get_key(password: str) -> bytes:
    digest = hashlib.sha256(password.encode('utf-8')).digest()
    return base64.urlsafe_b64encode(digest)

def decrypt_project(password: str, source_dirs: list):
    key = get_key(password)
    cipher = Fernet(key)
    
    success_count = 0
    
    for d in source_dirs:
        for root, _, files in os.walk(d):
            for file in files:
                if file.endswith(".enc"):
                    path = Path(root) / file
                    
                    try:
                        with open(path, "rb") as f:
                            encrypted_data = f.read()
                        
                        # Расшифровываем
                        decrypted = cipher.decrypt(encrypted_data)
                        py_path = path.with_suffix(".py")
                        
                        # Записываем исходный код обратно
                        with open(py_path, "wb") as f:
                            f.write(decrypted)
                        
                        # Удаляем .enc
                        os.remove(path)
                        success_count += 1
                        
                    except InvalidToken:
                        print(f"❌ Ошибка: Неверный пароль! Не удалось расшифровать {file}.")
                        return
                    except Exception as e:
                        print(f"❌ Ошибка чтения файла {file}: {e}")
                        return
                        
    if success_count > 0:
        print(f"✅ Успешно! Файлы возвращены в исходное состояние (.py). Восстановлено файлов: {success_count}")
    else:
        print("В папках не найдено файлов .enc для расшифровки.")

if __name__ == "__main__":
    pwd = input("Введите мастер-пароль для возврата файлов в .py: ")
    decrypt_project(pwd, ["src/ui", "src/core"])