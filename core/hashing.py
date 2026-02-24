import hashlib
import subprocess
from pathlib import Path
from typing import Union, Optional


def calculate_file_hash(filepath: Union[str, Path], algorithm: str = 'sha512', chunk_size: int = 8192) -> str:
    """Calcula o hash de um arquivo lendo em chunks."""
    filepath = Path(filepath)
    hasher = hashlib.new(algorithm)
    
    with filepath.open('rb') as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
            
    return hasher.hexdigest()


def calculate_stream_hash(filepath: Union[str, Path], stream_type: str = 'a', 
                          stream_index: int = 0, algorithm: str = 'sha512') -> Optional[str]:
    """
    Calcula o hash de um fluxo específico dentro de um container usando FFmpeg.
    
    Args:
        filepath: Caminho do arquivo.
        stream_type: Tipo do fluxo ('a' para áudio, 'v' para vídeo).
        stream_index: Índice do fluxo (ex: 0 para o primeiro fluxo).
        algorithm: Algoritmo de hash (ex: 'sha512').
        
    Returns:
        O hash em hexadecimal ou None se falhar.
    """
    try:
        cmd = [
            "ffmpeg", "-v", "quiet", "-i", str(filepath),
            "-map", f"0:{stream_type}:{stream_index}",
            "-f", "hash", "-hash", algorithm, "-"
        ]
        
        # FFmpeg escreve o hash no stdout no formato: ALGORITHM=HASH
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        output = result.stdout.strip()
        
        if "=" in output:
            return output.split("=")[1].strip()
        
        return None
    except Exception:
        return None
