import hashlib
import base64
import os

# Clé partagée par défaut sur le réseau local (32 octets encodés en base64 URL-safe)
DEFAULT_LAN_SECRET = b"MessagerLAN_SUPPTIC_2026_SecretKey!"


def compute_sha256_bytes(data: bytes) -> str:
    """Calcule l'empreinte SHA-256 hexadécimale d'un bloc d'octets."""
    return hashlib.sha256(data).hexdigest()


def compute_sha256_file(file_path: str, chunk_size: int = 65536) -> str:
    """Calcule l'empreinte SHA-256 d'un fichier complet par lecture en blocs."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            sha256.update(chunk)
    return sha256.hexdigest()


def verify_file_integrity(file_path: str, expected_sha256: str) -> bool:
    """Vérifie que l'empreinte SHA-256 du fichier reçu correspond à celle attendue."""
    if not os.path.exists(file_path):
        return False
    actual_sha256 = compute_sha256_file(file_path)
    return actual_sha256.lower() == expected_sha256.lower()


def _derive_xor_key(secret: bytes = DEFAULT_LAN_SECRET) -> bytes:
    """Dérive une clé de 32 octets via SHA-256 pour le chiffrement de flux."""
    return hashlib.sha256(secret).digest()


def encrypt_payload(raw_bytes: bytes, secret: bytes = DEFAULT_LAN_SECRET) -> bytes:
    """
    Chiffre les données avant envoi sur le socket TCP.
    Utilise Fernet (AES) si 'cryptography' est installé, sinon un chiffrement XOR-SHA256 rapide.
    """
    try:
        from cryptography.fernet import Fernet

        key = base64.urlsafe_b64encode(_derive_xor_key(secret))
        return b"FERNET:" + Fernet(key).encrypt(raw_bytes)
    except ImportError:
        key = _derive_xor_key(secret)
        xored = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw_bytes))
        return b"XOR256:" + xored


def decrypt_payload(encrypted_bytes: bytes, secret: bytes = DEFAULT_LAN_SECRET) -> bytes:
    """Déchiffre les données reçues depuis le socket TCP."""
    if encrypted_bytes.startswith(b"FERNET:"):
        from cryptography.fernet import Fernet

        key = base64.urlsafe_b64encode(_derive_xor_key(secret))
        return Fernet(key).decrypt(encrypted_bytes[7:])
    elif encrypted_bytes.startswith(b"XOR256:"):
        payload = encrypted_bytes[7:]
        key = _derive_xor_key(secret)
        return bytes(b ^ key[i % len(key)] for i, b in enumerate(payload))
    return encrypted_bytes


if __name__ == "__main__":
    # Test autonome rapide de crypto_utils.py
    msg = "Test d'intégrité et de chiffrement LAN".encode("utf-8")
    digest = compute_sha256_bytes(msg)
    chiffre = encrypt_payload(msg)
    dechiffre = decrypt_payload(chiffre)

    print(f"SHA-256   : {digest}")
    print(f"Chiffré   : {chiffre[:40]}...")
    print(f"Déchiffré : {dechiffre.decode('utf-8')}")
    assert msg == dechiffre, "Erreur de déchiffrement !"
    print("OK - Module crypto_utils validé.")