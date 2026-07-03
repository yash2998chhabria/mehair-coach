from cryptography.fernet import Fernet


def generate_key() -> str:
    return Fernet.generate_key().decode("ascii")


class TokenCipher:
    def __init__(self, key: str):
        if not key:
            raise ValueError(
                "TOKEN_ENCRYPTION_KEY is required. Generate one with: "
                "uv run python -m app.crypto"
            )
        self._fernet = Fernet(key.encode("ascii"))

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        return self._fernet.decrypt(value.encode("ascii")).decode("utf-8")


if __name__ == "__main__":
    print(generate_key())
