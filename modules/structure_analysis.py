import json
import struct
from pathlib import Path

from core.case_manager import CaseManager


class StructureAnalysisModule:
    """
    Análise de Estrutura Física de Arquivos MP4/MOV (ISO BMFF).
    Identifica a ordem dos átomos para inferir origem (Captura vs Edição/Streaming).
    """

    def __init__(self, case_manager: CaseManager):
        self.cm = case_manager
        self.logger = self.cm.get_logger()

    def run(self, input_file: Path, output_filename: str = "structure_analysis.json"):
        self.logger.log("STRUCT_START", {"file": input_file.name})
        
        try:
            atoms = self._parse_atoms(input_file)
            analysis = self._analyze_structure(atoms)
            
            result = {
                "atoms": atoms,
                "analysis": analysis
            }

            out_path = self.cm.results_dir / output_filename
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=4)
                
            self.logger.log("STRUCT_SUCCESS", {"atoms_found": len(atoms)})
            return result
            
        except Exception as e:
            self.logger.log("STRUCT_ERROR", {"error": str(e)})
            return {"error": str(e)}

    def _parse_atoms(self, input_file: Path):
        """
        Lê os átomos de nível superior do arquivo.
        """
        atoms = []
        file_size = input_file.stat().st_size
        
        with open(input_file, 'rb') as f:
            offset = 0
            while offset < file_size:
                f.seek(offset)
                header = f.read(8)
                if len(header) < 8:
                    break
                
                size, type_bytes = struct.unpack(">I4s", header)
                atom_type = type_bytes.decode('ascii', errors='ignore')
                
                # Handle large atoms (size=1 means 64-bit size follows)
                if size == 1:
                    large_size_data = f.read(8)
                    if len(large_size_data) < 8:
                        break
                    size = struct.unpack(">Q", large_size_data)[0]
                elif size == 0:
                    # Size 0 means atom extends to end of file
                    size = file_size - offset

                # Tamanho menor que o próprio cabeçalho indica arquivo
                # malformado — abortar evita loop infinito (offset não avança).
                if size < 8:
                    break

                atoms.append({
                    "type": atom_type,
                    "offset": offset,
                    "size": size
                })
                
                offset += size
                
        return atoms

    def _analyze_structure(self, atoms):
        """
        Interpreta a ordem dos átomos.
        """
        atom_types = [a['type'] for a in atoms]
        
        # Check moov vs mdat order
        moov_idx = -1
        mdat_idx = -1
        
        if 'moov' in atom_types:
            moov_idx = atom_types.index('moov')
        if 'mdat' in atom_types:
            mdat_idx = atom_types.index('mdat')
            
        conclusion = "Estrutura Indefinida"
        details = ""
        
        if moov_idx != -1 and mdat_idx != -1:
            if moov_idx < mdat_idx:
                conclusion = "Fast-Start (Streamable/Edited)"
                details = "O átomo de metadados ('moov') precede os dados de mídia ('mdat'). Isso é típico de arquivos otimizados para streaming web ou exportados por softwares de edição modernos (Premiere, Handbrake, FFmpeg faststart)."
            else:
                conclusion = "Recording Alignment (Capture)"
                details = "O átomo de metadados ('moov') está após os dados de mídia ('mdat'). Isso é característico de captura em tempo real (câmeras), onde os metadados só podem ser escritos após o término da gravação."
        elif moov_idx == -1:
             conclusion = "Incompleto/Stream Fragmentado"
             details = "Átomo 'moov' não encontrado no nível superior."
             
        return {
            "order": atom_types,
            "conclusion": conclusion,
            "interpretation": details
        }
