import hashlib
from pathlib import Path
from typing import Union


def calculate_file_hash(filepath: Union[str, Path], algorithm: str = 'sha512', chunk_size: int = 8192) -> str:
    """Calcula o hash de um arquivo lendo em chunks."""
    filepath = Path(filepath)
    hasher = hashlib.new(algorithm)
    
    with filepath.open('rb') as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
            
    return hasher.hexdigest()
