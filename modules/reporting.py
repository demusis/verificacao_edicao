import contextlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import ClassVar

from core.case_manager import CaseManager
from core.subprocess_utils import run_command
from core.utils import get_timestamp_iso


class ReportingModule:
    """Gerador de Relatórios (LaTeX -> PDF)."""
    
    def __init__(self, case_manager: CaseManager, config: dict | None = None):
        self.cm = case_manager
        self.logger = self.cm.get_logger()
        # Prioridade: Config injetada > Config do arquivo > Dict vazio
        self.config = config if config is not None else (self._load_config() or {})
        
        # Converter objeto AnalysisConfig para dict se necessário
        if hasattr(self.config, 'to_dict'):
            self.config = self.config.to_dict()

    def _load_config(self):
        config_path = Path("config.json")
        if config_path.exists():
            try:
                with open(config_path, encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _format_date(self, iso_str):
        """Formata data ISO para legível com timezone."""
        try:
            dt = datetime.fromisoformat(iso_str)
            return dt.strftime(r"%d/%m/%Y %H:%M (UTC%z)")
        except Exception:
            return iso_str

    def generate(self):
        self.logger.log("REPORT_GEN_START")
        
        # Coletar dados dos resultados
        data = self._collect_data()
        
        # Gerar LaTeX Source (Consolidado)
        tex_path = self.cm.report_dir / "report_consolidado.tex"
        latex_content = self._generate_latex_source(data)
        
        with open(tex_path, 'w', encoding='utf-8') as f:
            f.write(latex_content)
        
        self.logger.log("REPORT_TEX_GENERATED", {"path": str(tex_path)})
            
        # Compilar para PDF (Consolidado)
        pdf_path = self.cm.report_dir / "report_consolidado.pdf"
        try:
            self._compile_latex(tex_path, self.cm.report_dir)
            self.logger.log("REPORT_PDF_GENERATED", {"path": str(pdf_path)})
        except Exception as e:
            self.logger.log("REPORT_COMPILATION_ERROR", {"error": str(e)})
            print(f"ERRO AO COMPILAR PDF: {e}")
            print("O arquivo .tex foi gerado e pode ser compilado manualmente.")

    def generate_individual(self, idx: int, manifest_entry: dict):
        """Gera o PDF individual de um arquivo gradualmente (real-time)."""
        file_name = manifest_entry.get('filename', 'Unknown')
        file_entry = {
            "filename": file_name, 
            "thumbnail": manifest_entry.get('thumbnail'),
            "analyses": {}
        }
        
        # Carregar cada JSON de análise referenciado no manifesto
        for analysis_type, json_filename in manifest_entry.get('analysis_files', {}).items():
            json_path = self.cm.results_dir / json_filename
            if json_path.exists():
                try:
                    with open(json_path, encoding='utf-8') as jf:
                        file_entry["analyses"][analysis_type] = json.load(jf)
                except Exception as e:
                    self.logger.log("INDIVIDUAL_DATA_LOAD_ERROR", {"file": json_filename, "error": str(e)})

        single_data = {
            "case_name": f"{self.cm.case_name} - Análise Individual {idx+1}",
            "timestamp": get_timestamp_iso(),
            "files": [file_entry]
        }
        
        pdf_base_name = f"relatorio_{idx+1:02d}_{Path(file_name).stem}"
        tex_ind_path = self.cm.report_dir / f"{pdf_base_name}.tex"
        
        latex_ind_content = self._generate_latex_source(single_data)
        
        with open(tex_ind_path, 'w', encoding='utf-8') as f:
            f.write(latex_ind_content)
        self.logger.log("REPORT_INDIVIDUAL_TEX_GENERATED", {"path": str(tex_ind_path)})
        
        try:
            self._compile_latex(tex_ind_path, self.cm.report_dir)
            pdf_ind_path = self.cm.report_dir / f"{pdf_base_name}.pdf"
            self.logger.log("REPORT_INDIVIDUAL_PDF_GENERATED", {"path": str(pdf_ind_path)})
        except Exception as e:
            self.logger.log("REPORT_IND_COMP_ERROR", {"file": pdf_base_name, "error": str(e)})  


    def generate_prnu_comparison(self, comparison_data: dict):
        """Gera relatório PDF de comparação PRNU entre arquivos externos e existentes."""
        esc = self._escape_latex
        
        timestamp = comparison_data.get('timestamp', get_timestamp_iso())
        external_files = comparison_data.get('external_files', [])
        existing_files = comparison_data.get('existing_files', [])
        results = comparison_data.get('results', [])
        
        latex = r"""
\documentclass[a4paper,12pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage{textcomp}
\usepackage{float}
\usepackage[brazil]{babel}
\usepackage{geometry}
\usepackage{xcolor}
\usepackage{booktabs}
\usepackage{longtable}
\usepackage{graphicx}
\usepackage{hyperref}
\usepackage{tcolorbox}
\usepackage{fancyhdr}
\usepackage{xurl}

\newcommand{\rowcolor}[1]{}
\newcommand{\blackurl}[1]{{\hypersetup{urlcolor=black}\url{#1}}}

\definecolor{primary}{HTML}{2C3E50}
\definecolor{secondary}{HTML}{3498DB}
\definecolor{accent}{HTML}{E67E22}
\definecolor{lightgray}{HTML}{ECF0F1}
\definecolor{success}{HTML}{2ECC71}
\definecolor{danger}{HTML}{E74C3C}
\definecolor{warning}{HTML}{F1C40F}

\geometry{top=2.5cm, bottom=2.5cm, left=2.5cm, right=2.5cm}

\hypersetup{
    colorlinks=true,
    linkcolor=primary,
    filecolor=secondary,
    urlcolor=secondary,
}

\pagestyle{fancy}
\fancyhf{}
\lhead{\small \textcolor{gray}{Relatório de Comparação PRNU}}
\rhead{}
\cfoot{\thepage}

\title{\textbf{\textcolor{primary}{Relatório de Comparação PRNU\\(Identificação de Fonte)}}}
\date{}

\begin{document}

\maketitle

\section*{Resumo do Protocolo}
\begin{tcolorbox}[colback=lightgray,colframe=primary,title=Identificação]
\textbf{Tipo:} Comparação Direcionada de PRNU \\
\textbf{Caso:} """ + esc(self.cm.case_name) + r""" \\
\textbf{Data da Análise:} """ + self._format_date(timestamp) + r""" \\
\textbf{Arquivos Investigados:} """ + str(len(external_files)) + r""" \\
\textbf{Arquivos de Referência:} """ + str(len(existing_files)) + r"""
\end{tcolorbox}

\tableofcontents
\newpage
"""
        # --- Metodologia ---
        latex += r"\section{Metodologia}"
        latex += r"\begin{tcolorbox}[colback=lightgray,title=Metodologia Forense (PRNU)]"
        latex += r"\textbf{Fingerprint de Sensor:} O PRNU (\textit{Photo Response Non-Uniformity}) é um ruído imperceptível e único gerado pelas imperfeições físicas na fabricação do sensor de cada câmera. "
        latex += r"Ele funciona como uma 'impressão digital digital' da câmera."
        latex += r"\vspace{0.2cm}"
        latex += r"\\ \textbf{Correlação PCE:} A comparação utiliza a métrica \textbf{PCE} (\textit{Peak-to-Correlation Energy}). "
        latex += r"Calculamos o quanto o ruído de um arquivo se alinha estatisticamente com o de outro. Valores altos provam cientificamente que as mídias foram gravadas pelo mesmo dispositivo físico."
        latex += r"\end{tcolorbox}"
        
        latex += r"\begin{tcolorbox}[colback=white,colframe=secondary,title=Interpretação dos Valores PCE]"
        latex += r"A confiabilidade da identificação de fonte baseia-se nos seguintes limiares técnicos:"
        latex += r"\begin{itemize}[leftmargin=1cm]"
        latex += r"\item \textbf{PCE > 60:} \textbf{MATCH POSITIVO.} Fortíssima evidência de mesma origem. A probabilidade de erro (falso positivo) é estatisticamente desprezível."
        latex += r"\item \textbf{PCE 40 - 60:} \textbf{Indício Forte.} Alta probabilidade de mesma origem, mas recomendável buscar evidências complementares (ex: metadados)."
        latex += r"\item \textbf{PCE < 40:} \textbf{Inconclusivo.} O ruído pode estar muito degradado por compressão agressiva, redimensionamento ou falta de luz, impedindo a correlação segura."
        latex += r"\end{itemize}"
        latex += r"\vspace{0.2cm}"
        latex += r"\textbf{Nota sobre Resize:} Se os arquivos têm resoluções diferentes, o sistema redimensiona os fingerprints para permitir a comparação. Isso pode reduzir o score PCE e é sinalizado com um asterisco (*)."
        latex += r"\end{tcolorbox}"
        
        latex = self._add_refs(latex, "PRNU")
        
        # --- Legenda de Arquivos ---
        latex += r"\section{Identificação dos Arquivos}"
        
        latex += r"\subsection*{Arquivos Investigados (Externos)}"
        latex += r"\begin{center}\begin{tabular}{l p{12cm}}"
        latex += r"\toprule \textbf{ID} & \textbf{Arquivo} \\ \midrule "
        for i, fname in enumerate(external_files):
            fname_clean = r"\blackurl{" + str(fname) + r"}"
            latex += f"E{i+1} & {fname_clean} \\\\ \n"
        latex += r"\bottomrule \end{tabular}\end{center}"
        
        latex += r"\vspace{0.5cm}"
        
        latex += r"\subsection*{Arquivos de Referência (Diretório de Trabalho)}"
        latex += r"\begin{longtable}[c]{l p{12cm}}"
        latex += r"\toprule \textbf{ID} & \textbf{Arquivo} \\ \midrule "
        latex += r"\endhead "
        for i, fname in enumerate(existing_files):
            fname_clean = r"\blackurl{" + str(fname) + r"}"
            latex += f"R{i+1} & {fname_clean} \\\\ \n"
        latex += r"\bottomrule \end{longtable}"
        
        # --- Resultados ---
        latex += r"\section{Resultados da Comparação}"
        
        # Tabela resumo
        latex += r"\subsection{Tabela Geral de Comparações (PCE)}"
        latex += r"\begin{longtable}[c]{c c c l}"
        latex += r"\toprule \textbf{Investigado} & \textbf{Referência} & \textbf{Score PCE} & \textbf{Resultado} \\ \midrule "
        latex += r"\endhead "
        
        has_any_match = False
        
        for res_entry in results:
            ext_name = res_entry.get("external_file", "?")
            ext_idx = (external_files.index(ext_name) + 1) if ext_name in external_files else "?"
            
            for comp in res_entry.get("comparisons", []):
                exist_name = comp.get("existing_file", "?")
                exist_idx = (existing_files.index(exist_name) + 1) if exist_name in existing_files else "?"
                
                pce = comp.get("pce", 0)
                match = comp.get("match", False)
                note = comp.get("scaling_note")
                error = comp.get("error")
                
                if error:
                    pce_str = "Erro"
                    result_str = esc(str(error)[:30])
                    result_color = "black"
                else:
                    pce_str = f"{pce:.1f}"
                    if note:
                        pce_str += "*"
                    
                    if match:
                        result_str = r"\textbf{MATCH}"
                        result_color = "success"
                        has_any_match = True
                    elif pce > 40:
                        result_str = r"\textbf{Indício Forte}"
                        result_color = "warning"
                    else:
                        result_str = "Inconclusivo"
                        result_color = "black"
                
                latex += f"E{ext_idx} & R{exist_idx} & {pce_str} & \\textcolor{{{result_color}}}{{{result_str}}} \\\\ \\hline \n"
        
        latex += r"\bottomrule \end{longtable}"
        latex += r"\vspace{0.2cm}"
        latex += r"\small \textit{* Asterisco indica redimensionamento de fingerprint para compatibilizar resoluções distintas.}"
        
        # --- Detalhamento por arquivo investigado ---
        latex += r"\subsection{Detalhamento por Arquivo Investigado}"
        
        for res_entry in results:
            ext_name = res_entry.get("external_file", "?")
            
            latex += f"\\subsubsection{{\\texttt{{{self._escape_latex(ext_name)}}}}}"
            
            comparisons = res_entry.get("comparisons", [])
            
            # Ordenar por PCE decrescente
            sorted_comps = sorted(comparisons, key=lambda x: x.get("pce", 0), reverse=True)
            
            if sorted_comps:
                best = sorted_comps[0]
                best_pce = best.get("pce", 0)
                best_match = best.get("match", False)
                best_name = best.get("existing_file", "?")
                
                if best_match:
                    latex += r"\begin{tcolorbox}[colback=success!10,colframe=success,title=\textbf{MATCH Identificado}]"
                    latex += f"\\textbf{{Maior correlação:}} \\blackurl{{{best_name}}} com PCE = \\textbf{{{best_pce:.1f}}}. "
                    latex += r"Forte evidência de que ambos os arquivos foram capturados pelo \textbf{mesmo dispositivo físico}."
                    latex += r"\end{tcolorbox}"
                elif best_pce > 40:
                    latex += r"\begin{tcolorbox}[colback=warning!10,colframe=warning,title=Indício Encontrado]"
                    latex += f"\\textbf{{Maior correlação:}} \\blackurl{{{best_name}}} com PCE = \\textbf{{{best_pce:.1f}}}. "
                    latex += r"Há indício de mesma origem, mas o score não atinge o limiar de certeza (60)."
                    latex += r"\end{tcolorbox}"
                else:
                    latex += r"\begin{tcolorbox}[colback=lightgray,colframe=gray,title=Nenhum Match Identificado]"
                    latex += f"\\textbf{{Maior correlação:}} \\blackurl{{{best_name}}} com PCE = \\textbf{{{best_pce:.1f}}}. "
                    latex += r"Nenhum dos arquivos de referência apresentou correlação significativa com este arquivo."
                    latex += r"\end{tcolorbox}"
            
            # Tabela ranking
            latex += r"\begin{longtable}[c]{c l c l}"
            latex += r"\toprule \textbf{Rank} & \textbf{Arquivo de Referência} & \textbf{PCE} & \textbf{Status} \\ \midrule "
            latex += r"\endhead "
            
            for rank, comp in enumerate(sorted_comps, 1):
                exist_name = comp.get("existing_file", "?")
                pce = comp.get("pce", 0)
                match = comp.get("match", False)
                note = comp.get("scaling_note")
                
                pce_str = f"{pce:.1f}"
                if note:
                    pce_str += "*"
                
                if match:
                    status = r"\textcolor{success}{\textbf{MATCH}}"
                elif pce > 40:
                    status = r"\textcolor{warning}{\textbf{Indício}}"
                else:
                    status = "Inconclusivo"
                
                latex += f"{rank} & \\blackurl{{{exist_name}}} & {pce_str} & {status} \\\\ \\hline \n"
            
            latex += r"\bottomrule \end{longtable}"
        
        # --- Conclusão Geral ---
        latex += r"\section{Conclusão}"
        
        if has_any_match:
            latex += r"\begin{tcolorbox}[colback=success!10,colframe=success,title=Conclusão Geral]"
            latex += r"\textbf{Match(es) positivo(s) identificado(s).} "
            latex += r"Um ou mais arquivos investigados apresentaram forte correlação PRNU com arquivos de referência, "
            latex += r"indicando com alto grau de confiança que foram capturados pelo mesmo dispositivo físico."
            latex += r"\end{tcolorbox}"
        else:
            latex += r"\begin{tcolorbox}[colback=lightgray,colframe=gray,title=Conclusão Geral]"
            latex += r"Nenhum match conclusivo foi identificado entre os arquivos investigados e os de referência. "
            latex += r"Os scores PCE obtidos são insuficientes para afirmar que os arquivos compartilham a mesma fonte de captação."
            latex += r"\end{tcolorbox}"
        
        latex = self._add_refs(latex, "PRNU")
        
        # --- Parâmetros ---
        latex += r"\newpage"
        latex += r"\section{Parâmetros de Configuração}"
        latex += r"Para fins de auditabilidade e reprodutibilidade, seguem os parâmetros técnicos utilizados:"
        latex += r"\begin{itemize}"
        
        prnu_limit = self.config.get('prnu_frame_limit', 30) if isinstance(self.config, dict) else 30
        latex += f"\\item \\textbf{{Limite de Quadros PRNU:}} {prnu_limit}"
        latex += r"\item \textbf{Limiar de Match (PCE):} 60.0"
        latex += r"\end{itemize}"
        
        latex += r"\end{document}"
        
        # Normalizar quebras de linha para compilação LaTeX correta
        # (previne erros do enumitem/babel quando comandos ficam concatenados)
        for _cmd in [r'\begin{', r'\end{', r'\section', r'\subsection',
                     r'\subsubsection', r'\item ', r'\newpage', r'\noindent']:
            latex = latex.replace(_cmd, '\n' + _cmd)
        latex = re.sub(r'\n{3,}', '\n\n', latex)
        
        # Remover opções do enumitem (incompatível com algumas instalações MiKTeX)
        latex = re.sub(r'\\begin\{itemize\}\[[^\]]*\]', r'\\begin{itemize}', latex)
        
        # Escrever e compilar
        tex_path = self.cm.report_dir / "prnu_comparison.tex"
        with open(tex_path, 'w', encoding='utf-8') as f:
            f.write(latex)
        
        self.logger.log("PRNU_COMPARISON_TEX_GENERATED", {"path": str(tex_path)})
        
        try:
            self._compile_latex(tex_path, self.cm.report_dir)
            pdf_path = self.cm.report_dir / "prnu_comparison.pdf"
            self.logger.log("PRNU_COMPARISON_PDF_GENERATED", {"path": str(pdf_path)})
        except Exception as e:
            self.logger.log("PRNU_COMPARISON_COMP_ERROR", {"error": str(e)})
            print(f"ERRO AO COMPILAR PDF: {e}")
            print("O arquivo .tex foi gerado e pode ser compilado manualmente.")

    def _collect_data(self):
        base_data = {
            "case_name": self.cm.case_name,
            "timestamp": get_timestamp_iso(),
            "files": []
        }
        
        manifest_path = self.cm.results_dir / "batch_manifest.json"
        
        if manifest_path.exists():
            # Modo Batch
            try:
                with open(manifest_path, encoding='utf-8') as f:
                    manifest = json.load(f)
                    
                for item in manifest:
                    file_name = item.get('filename', 'Unknown')
                    file_entry = {
                        "filename": file_name, 
                        "thumbnail": item.get('thumbnail'),
                        "analyses": {}
                    }
                    
                    # Carregar cada JSON de análise referenciado no manifesto
                    for analysis_type, json_filename in item.get('analysis_files', {}).items():
                        json_path = self.cm.results_dir / json_filename
                        if json_path.exists():
                            with open(json_path, encoding='utf-8') as jf:
                                file_entry["analyses"][analysis_type] = json.load(jf)
                                
                    base_data["files"].append(file_entry)
            except Exception as e:
                self.logger.log("MANIFEST_LOAD_ERROR", {"error": str(e)})
                
            # Carregar Matriz PRNU (se existir)
            matrix_path = self.cm.results_dir / "prnu_matrix.json"
            if matrix_path.exists():
                try:
                    with open(matrix_path, encoding='utf-8') as f:
                        base_data["prnu_matrix"] = json.load(f)
                except Exception as e:
                    self.logger.log("PRNU_MATRIX_LOAD_ERROR", {"error": str(e)})
        else:
            # Modo Legado / Arquivo Único
            single_entry = {"filename": "Arquivo Único", "analyses": {}}
            
            # Mapeamento de nomes de arquivo padrão para chaves de análise
            for res_file in self.cm.results_dir.glob("*.json"):
                if res_file.name == "batch_manifest.json":
                    continue
                
                # Ex: file_analysis.json -> file_analysis
                key = res_file.stem
                try:
                    with open(res_file, encoding='utf-8') as f:
                        single_entry["analyses"][key] = json.load(f)
                except Exception as e:
                    self.logger.log("DATA_LOAD_ERROR", {"file": res_file.name, "error": str(e)})
            
            if single_entry["analyses"]:
                base_data["files"].append(single_entry)
        
        return base_data

    # Banco de Referências Bibliográficas (ABNT)
    REFERENCES_DB: ClassVar[dict[str, list[str]]] = {
        "ELA": [
            r"KRAWETZ, N. A Picture's Worth: Digital Image Analysis and Forensics. In: \textit{Black Hat Briefings}, Las Vegas, 2007.",
            r"LIN, Z. et al. Fast, Automatic and Fine-Grained Tampered JPEG Image Detection via DCT Coefficient Analysis. \textit{Pattern Recognition}, 2009."
        ],
        "PRNU": [
            r"YU, P. et al. A survey on deepfake video detection. \textit{Iet Biometrics}, v. 10, n. 6, p. 607-624, 2021.",
            r"LUKAS, J.; FRIDRICH, J.; GOLJAN, M. Digital Camera Identification From Sensor Pattern Noise. \textit{IEEE Transactions on Information Forensics and Security}, v. 1, n. 2, p. 205-214, 2006."
        ],
        "COPYMOVE": [
            r"AMERINI, I. et al. A SIFT-Based Forensic Method for Copy-Move Attack Detection and Transformation Recovery. \textit{IEEE Transactions on Information Forensics and Security}, v. 6, n. 3, p. 1099-1110, 2011.",
            r"CHRISTLEIN, V. et al. An Evaluation of Popular Copy-Move Forgery Detection Approaches. \textit{IEEE Transactions on Information Forensics and Security}, v. 7, n. 6, p. 1841-1854, 2012."
        ],
        "RESAMPLING": [
            r"KADHA, V.; BAKSHI, S; DAS, S. K. Unravelling digital forgeries: A systematic survey on image manipulation detection and localization. \textit{ ACM Computing Surveys}, v. 57, n. 12, p. 1-36, 2025.",
            r"MAHDIAN, B.; SAIC, S. Blind Authentication Using Periodic Properties of Interpolation. \textit{IEEE Transactions on Information Forensics and Security}, v. 3, n. 3, p. 529-538, 2008."
        ],
        "JPEG": [
            r"FARID, H. Exposing Digital Forgeries From JPEG Ghosts. \textit{IEEE Transactions on Information Forensics and Security}, v. 4, n. 1, p. 154-160, 2009.",
            r"FAN, Z.; DE QUEIROZ, R. L. Identification of Bitmap Compression History: JPEG Detection and Quantizer Estimation. \textit{IEEE Transactions on Image Processing}, v. 12, n. 2, p. 230-235, 2003."
        ],
        "NOISE": [
            r"MAHDIAN, B.; SAIC, S. Using Noise Inconsistencies for Blind Image Forensics. \textit{Image and Vision Computing}, v. 27, n. 10, p. 1497-1503, 2009."
        ],
        "DCT": [
            r"SWAMINATHAN, A. et al. Digital Image Forensics via Intrisic Fingerprints. \textit{IEEE Transaktions on Information Forensic and Security}, v. 3, n. 1, p. 101-117, 2008.",
            r"LIN, Z. et al. Fast, Automatic and Fine-Grained Tampered JPEG Image Detection via DCT Coefficient Analysis. \textit{Pattern Recognition}, v. 42, n. 11, p. 2492-2501, 2009."
        ],
         "COMPRESSION": [
            r"WANG, W.; FARID, H. Exposing Digital Forgeries in Video by Detecting Double MPEG Compression. In: \textit{Proceedings of the 8th Workshop on Multimedia and Security}. ACM, 2006. p. 37-47."
        ],
        "DEEPFAKE": [
            r"DURALL, R. et al. Watch your Up-Convolution: CNN Based Generative Models Yield Artificial Frequency Patterns. \textit{Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition}, 2020.",
        ],
        "PROCESSING": [
            r"DIAS, Z.; ROCHA, A.; GOLDENSTEIN, S. Image Phylogeny by Minimal Spanning Trees. \textit{IEEE Transactions on Information Forensics and Security}, v. 7, n. 2, p. 774-788, 2012.",
            r"MILANI, S. et al. An Overview on Video Forensics. \textit{APSIPA Transactions on Signal and Information Processing}, v. 1, e2, 2012."
        ],
        "GOP": [
            r"VAZQUEZ-PADIN, D. et al. Video Integrity Verification using GOP Structure Analysis. \textit{IEEE International Workshop on Information Forensics and Security (WIFS)}, 2012.",
            r"BESTAGINI, P. et al. Video Codec Identification via GOP Analysis. \textit{IEEE International Conference on Acoustics, Speech and Signal Processing (ICASSP)}, 2012."
        ],
        "CONTINUITY": [
            r"STAMM, M. C. et al. Temporal forensics and anti-forensics for motion compensated video. \textit{IEEE Transactions on Information Forensics and Security}v. 7, n. 4, p. 1315-1329, 2012.",
            r"GIRONI, A. et al. A video forensic technique for detecting frame deletion and insertion. \textit{ In: 2014 IEEE International Conference on Acoustics, Speech and Signal Processing (ICASSP)}, IEEE, 2014. p. 6226-6230."
        ],
        "STRUCTURE": [
             r"MICHAŁEK, Marcin. Metadata in audio files compliant with ISO/IEC 14496-12 and their characteristics as well as the evaluation of usability in the investigation of the authenticity of recordings. \textit{Problems of Forensic Sciences}, v. 115, p. 241-261, 2018."
        ],
        "BENFORD_VIDEO": [
             r"VARGA, D. Benford's Law and Perceptual Features for Face Image Quality Assessment \textit{Signals 4}, no. 4: 859-876. https://doi.org/10.3390/signals4040047, 2023."
        ],
        "PERIODICITY": [
             r"BIANCHI, T. et al. Detection of Non-Aligned Double JPEG Compression with Estimation of Primary Compression Parameters. \textit{IEEE International Conference on Image Processing (ICIP)}, 2011.",
             r"WANG, W.; FARID, H. Exposing Digital Forgeries in Video by Detecting Double MPEG Compression. \textit{Proceedings of the 8th Workshop on Multimedia and Security}, ACM, 2006."
        ],
        "QUANTIZATION": [
             r"MANISHA, C. T. L.; KARUNAKAR, A. K. Source Camera Identification with a Robust Device Fingerprint: Evolution from Image-Based to Video-Based Approaches \textit{Sensors 23}, no. 17: 7385, 2023, https://doi.org/10.3390/s23177385",
             r"LAOUAMER, L. et al. Motion JPEG Video Authentication based on Quantization Matrix Watermarking: Application in Robotics. \textit{International Journal of Computer Applications}, v. 975, P. 8887, 2012."
        ],
        "AUDIO": [
             r"MAHER, R. C. Audio Forensic Examination: Authenticity, Enhancement, and Interpretation. \textit{IEEE Signal Processing Magazine}, v. 26, n. 2, 2009.",
             r"GRIGORAS, C. Digital Audio Forensics: Recording Analysis, Artifact Detection and Authentication. \textit{International Journal of Digital Crime and Forensics}, 2009."
        ],
        "AUDIO_DEEPFAKE": [
             r"FRANK, J. et al. WaveFake: A Data Set to Facilitate Audio Deepfake Detection. \textit{NeurIPS (Neural Information Processing Systems)}, 2021.",
             r"MULLER, N. et al. Does Audio Deepfake Detection Generalize? \textit{Interspeech}, 2022."
        ]
    }

    def _add_refs(self, latex, key):
        """Adiciona bloco de referências bibliográficas se existirem."""
        refs = self.REFERENCES_DB.get(key)
        if not refs:
            return latex
        
        latex += r"\par\vspace{0.3cm}"
        latex += r"\noindent \textbf{\footnotesize Referências do Procedimento:}"
        latex += r"\begin{itemize}[leftmargin=*,noitemsep]"
        for r in refs[:5]: # Max 5
            latex += r"\item \footnotesize " + r
        latex += r"\end{itemize}"
        latex += r"\vspace{0.5cm}"
        return latex

    def _escape_latex(self, text):
        """Escapa caracteres especiais do LaTeX."""
        if not isinstance(text, str):
            return str(text)
        
        chars = {
            '&': r'\&',
            '%': r'\%',
            '$': r'\$',
            '#': r'\#',
            '_': r'\_',
            '{': r'\{',
            '}': r'\}',
            '~': r'\textasciitilde{}',
            '^': r'\textasciicircum{}',
            '\\': r'\textbackslash{}'
        }
        return ''.join(chars.get(c, c) for c in text)

    def _compile_latex(self, tex_file: Path, output_dir: Path):
        """Executa pdflatex para compilar o arquivo .tex."""
        # Muda para o diretório de saída para evitar problemas de path com arquivos auxiliares (.aux, .toc)
        # Executa 3 vezes para garantir índices e referências
        
        cmd = [
            "pdflatex",
            "-interaction=nonstopmode",
            tex_file.name
        ]
        
        # Limpar auxiliares de compilações anteriores (previne erros de .aux corrompido)
        for ext in ['.aux', '.toc', '.out']:
            aux_path = output_dir / (tex_file.stem + ext)
            if aux_path.exists():
                with contextlib.suppress(Exception):
                    aux_path.unlink()
        
        for i in range(3):
            # cwd=str(output_dir) é crucial
            res = run_command(cmd, cwd=str(output_dir))
            if res.returncode != 0:
                if i == 0:
                    # Limpar auxiliares corrompidos pelo pass falho antes de tentar novamente
                    for ext in ['.aux', '.toc', '.out']:
                        aux_path = output_dir / (tex_file.stem + ext)
                        if aux_path.exists():
                            with contextlib.suppress(Exception):
                                aux_path.unlink()
                    continue
                raise RuntimeError(f"pdflatex failed (Pass {i+1}): {res.stderr or res.stdout}")

    def _generate_latex_source(self, data):
        """Gera o código fonte LaTeX completo."""
        esc = self._escape_latex
        
        latex = r"""
\documentclass[a4paper,12pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage{textcomp}
\usepackage{float}
\usepackage[brazil]{babel}
\usepackage{geometry}
\usepackage{xcolor}
\usepackage{booktabs}
\usepackage{longtable}
\usepackage{enumitem}
\usepackage{graphicx}
\usepackage{hyperref}
\usepackage{float}
\usepackage{float}
\usepackage{tcolorbox}
\usepackage{fancyhdr}
\usepackage{xurl} % Better than seqsplit for handling wrapping

% Define dummy rowcolor to avoid errors after removing colortbl
\newcommand{\rowcolor}[1]{}
\newcommand{\blackurl}[1]{{\hypersetup{urlcolor=black}\url{#1}}}

% Configuração de Cores
\definecolor{primary}{HTML}{2C3E50}
\definecolor{secondary}{HTML}{3498DB}
\definecolor{accent}{HTML}{E67E22}
\definecolor{lightgray}{HTML}{ECF0F1}
\definecolor{success}{HTML}{2ECC71}
\definecolor{danger}{HTML}{E74C3C}
\definecolor{warning}{HTML}{F1C40F}

\geometry{top=2.5cm, bottom=2.5cm, left=2.5cm, right=2.5cm}

% Configuração de Links
\hypersetup{
    colorlinks=true,
    linkcolor=primary,
    filecolor=secondary,
    urlcolor=secondary,
}

% Cabeçalho e Rodapé
\pagestyle{fancy}
\fancyhf{}
\lhead{\small \textcolor{gray}{Relatório Forense de Imagem/Vídeo}}
\rhead{}
\cfoot{\thepage}

\title{\textbf{\textcolor{primary}{Relatório de Análise Forense de Imagem/Vídeo}}}
\date{}

\begin{document}

\maketitle

\section*{Resumo do Protocolo}
\begin{tcolorbox}[colback=lightgray,colframe=primary,title=Identificação]
\textbf{Protocolo:} """ + esc(data['case_name']) + r""" \\
\textbf{Data da Análise:} """ + self._format_date(data['timestamp']) + r"""
\end{tcolorbox}

\tableofcontents
\newpage
"""
        # Loop por Arquivos
        for f_idx, file_entry in enumerate(data.get('files', []), 1):
            f_name_raw = file_entry.get('filename', 'Desconhecido')
            f_analyses = file_entry.get('analyses', {})
            
            # Use safe toc entry
            latex += f"\\section[Arquivo {f_idx}]{{Arquivo: \\blackurl{{{f_name_raw}}}}}\n"
            
            # --- THUMBNAIL ---
            thumb = file_entry.get('thumbnail')
            if thumb:
                 t_path = f"../results/{thumb}"
                 latex += r"\begin{figure}[H]"
                 latex += r"\centering"
                 latex += f"\\includegraphics[width=0.4\\textwidth]{{{t_path}}}"
                 latex += r"\caption{Quadro de Referência / Imagem Original}"
                 latex += r"\end{figure}"
            
            # --- 1. FILE ANALYSIS ---
            if 'file_analysis' in f_analyses and self.config.get('report_metadata', True):
                fa = f_analyses['file_analysis']
                meta = fa.get('metadata', {})
                fmt = meta.get('format', {})
                
                latex += r"\subsection{Metadados do Arquivo}"
                
                # Hash
                latex += r"\subsubsection*{Identificação Digital (Hash)}"
                latex += r"\begin{tcolorbox}[colback=white,colframe=gray]"
                # Use \url for safe wrapping using xurl package, forced to black color
                latex += r"\textbf{SHA-512:} \blackurl{" + fa.get('file_hash', 'N/A') + r"}"
                latex += r"\end{tcolorbox}"
                
                # Format Table
                latex += r"\subsubsection*{Formato e Container}"
                latex += r"\begin{longtable}{p{5cm} p{10cm}}"
                latex += r"\toprule \textbf{Propriedade} & \textbf{Valor} \\ \midrule "
                latex += r"\endhead "
                
                if not fmt:
                     latex += r"\multicolumn{2}{c}{\textbf{AVISO: Nenhum metadado de formato encontrado (Dicionário vazio).}} \\ \hline"
                
                for k, v in fmt.items():
                    # Force string conversion and basic cleanup
                    key_clean = esc(str(k))
                    
                    # Se for filename, mostrar apenas o basename para não quebrar tabela
                    if k == 'filename':
                        try:
                            val_str = os.path.basename(str(v))
                        except Exception:
                            val_str = str(v)
                    else:
                        val_str = str(v)
                        
                    val_clean = esc(val_str)
                    
                    if not isinstance(v, (dict, list)):
                        # Use small font for values
                        # For filename, use \blackurl to allow breaking anywhere (no hyphens)
                        if k == 'filename':
                             latex += f"\\textbf{{{key_clean}}} & \\small \\blackurl{{{val_str}}} \\\\ \\hline \n"
                        else:
                             latex += f"\\textbf{{{key_clean}}} & \\small {val_clean} \\\\ \\hline \n"
                latex += r"\bottomrule \end{longtable}"
                
                # --- 2. STREAMS ---
                streams = meta.get('streams', [])
                if streams:
                    latex += r"\subsection{Fluxos de Mídia (Streams)}"
                    for s in streams:
                        idx = s.get('index', '?')
                        ctype = esc(s.get('codec_type', 'unknown').upper())
                        latex += f"\\subsubsection*{{Stream \\#{idx}: {ctype}}}"
                        
                        latex += r"\begin{longtable}{p{5cm} p{10cm}}"
                        latex += r"\toprule \textbf{Propriedade} & \textbf{Valor} \\ \midrule "
                        latex += r"\endhead "
                        
                        # Prioridade
                        priority_keys = ['codec_name', 'profile', 'width', 'height', 'pix_fmt', 'sample_rate', 'channels', 'duration', 'bit_rate']
                        for k in priority_keys:
                            if k in s:
                                latex += f"\\textbf{{{esc(k)}}} & {esc(str(s[k]))} \\\\ \\hline \n"
                        
                        for k, v in s.items():
                            if k not in priority_keys and k != 'tags' and not isinstance(v, (dict, list)):
                                 latex += f"\\textbf{{{esc(k)}}} & {esc(str(v))[:100]} \\\\ \\hline \n"
                        
                        latex += r"\bottomrule \end{longtable}"

                # --- 3. PROCESSING TRACES ---
                proc = fa.get('processing_analysis', {})
                if proc:
                    latex += r"\subsection{Indícios de Múltiplos Processamentos}"
                    
                    latex += r"\begin{tcolorbox}[colback=lightgray,title=Metodologia: Análise de Traços de Processamento]"
                    latex += r"Investiga o \textit{container} do arquivo (Metadados e Estrutura) em busca de assinaturas digitais deixadas por softwares de edição, re-codificação ou muxing:"
                    latex += r"\begin{itemize}[leftmargin=1cm]"
                    latex += r"\item \textbf{Marcas de Software:} Identifica strings características de bibliotecas de edição (ex: FFmpeg, Lavf, Adobe) que não estão presentes em câmeras originais."
                    latex += r"\item \textbf{Histórico de Criação:} Analisa tags como \textit{compatible\_brands} e \textit{handler\_name} para rastrear a linhagem do arquivo (Filogenia Multimídia)."
                    latex += r"\end{itemize}"
                    latex += r"\end{tcolorbox}"
                    
                    conclusion = esc(proc.get('conclusion', ''))
                    is_detected = proc.get('detected', False)
                    color = "danger" if is_detected else "success"
                    
                    latex += r"\begin{tcolorbox}[colback=white,colframe=" + color + r",title=Avaliação Automática]"
                    latex += r"\textbf{" + conclusion + r"}"
                    latex += r"\end{tcolorbox}"
                    
                    traces = proc.get('traces_found', [])
                    if traces:
                        latex += r"\subsubsection*{Assinaturas de Software Encontradas}"
                        latex += r"\begin{longtable}{p{3.5cm} p{6.5cm} p{5.5cm}}"
                        latex += r"\toprule \textbf{Origem} & \textbf{Chave} & \textbf{Valor} \\ \midrule "
                        latex += r"\endhead "
                        for t in traces:
                            latex += f"{esc(t.get('source','-'))} & {esc(t.get('key','-'))} & {esc(str(t.get('value','-'))[:50])} \\\\ \\hline \n"
                        latex += r"\bottomrule \end{longtable}"
                
                latex = self._add_refs(latex, "PROCESSING")

                # --- 4. GOP ---
                gop = fa.get('gop_stats', {})
                if self.config.get('report_gop', True):
                    latex += r"\subsection{Estrutura de Compressão (GOP)}"
                
                    # Help Box - Expanded
                    latex += r"\begin{tcolorbox}[colback=lightgray,title=O que é GOP (Group of Pictures)?]"
                    latex += r"O \textit{Group of Pictures} (GOP) é a estrutura fundamental da compressão temporal em vídeos. "
                    latex += r"Ele define a distância entre \textbf{I-frames} (quadros de referência completos) e a organização dos quadros preditivos. "
                    latex += r"Alterações anormais na estrutura GOP podem indicar: "
                    latex += r"\begin{itemize}[leftmargin=1cm]"
                    latex += r"\item Recompressão ou re-encoding do vídeo (manipulação)"
                    latex += r"\item Uso de software de edição profissional"
                    latex += r"\item Streaming/upload (plataformas alteram GOP para otimizar transmissão)"
                    latex += r"\end{itemize}"
                    latex += r"\end{tcolorbox}"
                    
                    # Frame type explanations
                    latex += r"\subsubsection*{Tipos de Quadros}"
                    latex += r"\begin{itemize}[leftmargin=1cm]"
                    latex += r"\item \textbf{I-Frames (Intra):} Quadros completos, auto-contidos. Servem como \textit{keyframes} (pontos de referência). São os maiores em tamanho."
                    latex += r"\item \textbf{P-Frames (Preditivos):} Codificam apenas as diferenças em relação ao quadro anterior. Menores que I-frames."
                    latex += r"\item \textbf{B-Frames (Bi-direcionais):} Codificam diferenças em relação a quadros anteriores \textit{e posteriores}. Os menores, mas exigem mais processamento."
                    latex += r"\end{itemize}"
                    
                    # Statistics table
                    total_frames = gop.get('total_frames_analyzed', 0)
                    i_count = gop.get('i_frames', 0)
                    p_count = gop.get('p_frames', 0)
                    b_count = gop.get('b_frames', 0)
                    avg_gop = gop.get('avg_gop_size', 0)
                    
                    latex += r"\subsubsection*{Estatísticas Detectadas}"
                    latex += r"\begin{longtable}{p{7cm} p{3cm} p{5cm}}"
                    latex += r"\toprule \textbf{Métrica} & \textbf{Valor} & \textbf{Referência Típica} \\ \midrule "
                    latex += r"\endhead "
                    
                    latex += f"Total de Frames Analisados & {total_frames} & - \\\\ \\hline \n"
                    
                    # I-frames with interpretation
                    i_percent = (i_count / total_frames * 100) if total_frames > 0 else 0
                    i_ref = r"1-10\% (5-15 frames/seg em 30fps)"
                    i_status = ""
                    if i_percent < 0.5:
                        i_status = r" \textcolor{danger}{\textbf{ANORMAL - GOP extremamente longo}}"
                    elif i_percent < 2:
                        i_status = r" \textcolor{warning}{\textbf{Incomum - possível streaming}}"
                    
                    latex += f"I-Frames (Keyframes) & {i_count} ({i_percent:.1f}\\%) & {i_ref}{i_status} \\\\ \\hline \n"
                    
                    # P-frames
                    p_percent = (p_count / total_frames * 100) if total_frames > 0 else 0
                    p_ref = r"30-70\%"
                    latex += f"P-Frames (Preditivos) & {p_count} ({p_percent:.1f}\\%) & {p_ref} \\\\ \\hline \n"
                    
                    # B-frames
                    b_percent = (b_count / total_frames * 100) if total_frames > 0 else 0
                    b_ref = r"20-60\% (ausente em captura simples)"
                    latex += f"B-Frames (Bi-direcionais) & {b_count} ({b_percent:.1f}\\%) & {b_ref} \\\\ \\hline \n"
                    
                    # Average GOP size with interpretation
                    gop_ref = r"10-30 (captura); 60-300 (streaming)"
                    gop_status = ""
                    if avg_gop > 250:
                        gop_status = r" \textcolor{danger}{\textbf{EXTREMO - typical streaming}}"
                    elif avg_gop > 60:
                        gop_status = r" \textcolor{warning}{\textbf{Alto - possível plataforma online}}"
                    elif avg_gop < 10:
                        gop_status = r" \textcolor{warning}{\textbf{Baixo - edição profissional}}"
                    
                    latex += f"Tamanho Médio do GOP & {avg_gop:.2f} & {gop_ref}{gop_status} \\\\ \\hline \n"
                    
                    latex += r"\bottomrule \end{longtable}"
                    
                    # Forensic interpretation
                    latex += r"\subsubsection*{Interpretação Forense}"
                    latex += r"\begin{tcolorbox}[colback=white,colframe=secondary]"
                    
                    if i_count <= 1 and total_frames > 100:
                        latex += r"\textbf{ALERTA:} GOP extremamente longo detectado (apenas " + str(i_count) + r" I-frame). "
                        latex += r"Isso é \textbf{altamente incomum} e indica: "
                        latex += r"\begin{itemize}[leftmargin=1cm]"
                        latex += r"\item \textbf{Streaming de plataforma online} (YouTube, Facebook, etc. usam GOP de 120-300 para otimizar largura de banda)"
                        latex += r"\item \textbf{Compressão agressiva pós-processamento} (não é padrão de gravação de câmera)"
                        latex += r"\item \textbf{Possível re-encoding} (vídeo pode ter sido exportado de software de edição)"
                        latex += r"\end{itemize}"
                        latex += r"Vídeos capturados diretamente de câmeras/celulares normalmente têm GOP de 10-30 quadros (I-frame a cada 0.3-1 segundo)."
                    elif avg_gop > 60:
                        latex += r"GOP elevado detectado. Possível origem: streaming ou software de edição."
                    elif b_count == 0 and total_frames > 50:
                        latex += r"Ausência de B-frames. Padrão comum em captura direta de dispositivos móveis ou câmeras mais antigas."
                    else:
                        latex += r"Estrutura GOP dentro de parâmetros típicos para gravação direta."
                    
                    latex += r"\end{tcolorbox}"
                    
                    latex = self._add_refs(latex, "GOP")

            # --- 5. CONTINUITY ---
            if 'continuity_analysis' in f_analyses and self.config.get('report_continuity', True):
                ca = f_analyses['continuity_analysis']
                cuts = ca.get('cuts_detected', [])
                total = ca.get('total_cuts', 0)
                
                latex += r"\subsection{Análise de Continuidade Visual}"
                
                # Expanded educational box
                latex += r"\begin{tcolorbox}[colback=lightgray,title=Entendendo esta Análise]"
                latex += r"\textbf{Objetivo:} Detectar \textit{cortes bruscos} (hard cuts ou jump cuts) no vídeo através da análise de diferenças entre quadros consecutivos."
                latex += r"\vspace{0.2cm}"
                latex += r"\textbf{Metodologia:} A análise calcula a diferença pixel-a-pixel entre frames adjacentes. "
                latex += r"Quando a diferença excede um limiar estatístico, um corte é registrado. "
                latex += r"\vspace{0.2cm}"
                latex += r"\textbf{Interpretação Forense:}"
                latex += r"\begin{itemize}[leftmargin=1cm]"
                latex += r"\item \textbf{Gravação contínua autêntica:} Esperado \textbf{zero cortes} ou apenas transições suaves de câmera/cenário"
                latex += r"\item \textbf{Vídeo editado:} Presença de cortes bruscos indica junção de clipes diferentes, supressão de segmentos, ou montagem"
                latex += r"\item \textbf{Vídeo de vigilância manipulado:} Cortes são forte indício de exclusão de evidências"
                latex += r"\end{itemize}"
                latex += r"\vspace{0.2cm}"
                latex += r"\textbf{Limitações:} Esta análise detecta apenas descontinuidades \textit{visuais} óbvias. "
                latex += r"Manipulações sofisticadas (como substituição de frames com transições suaves) podem não ser detectadas aqui, "
                latex += r"mas serão identificadas pela análise de PTS/DTS abaixo."
                latex += r"\end{tcolorbox}"
                
                # Summary with interpretation
                cut_status = ""
                if total == 0:
                    cut_status = r" \textcolor{success}{\textbf{(Padrão esperado para gravação contínua)}}"
                elif total <= 3:
                    cut_status = r" \textcolor{warning}{\textbf{(Baixo - possível troca de cena legítima)}}"
                else:
                    cut_status = r" \textcolor{danger}{\textbf{(Alto - forte indício de edição)}}"
                
                latex += r"\vspace{0.3cm}"
                latex += f"\\textbf{{Resumo:}} Foram detectadas \\textbf{{{total}}} descontinuidades visuais{cut_status}."
                latex += r"\vspace{0.3cm}"
                
                if cuts:
                    latex += r"\subsubsection*{Tabela de Cortes}"
                    latex += r"\begin{longtable}{l l l l}"
                    latex += r"\toprule \textbf{Timestamp} & \textbf{Frame} & \textbf{PTS} & \textbf{Tipo} \\ \midrule "
                    latex += r"\endhead "
                    for c in cuts:
                        # Format time MM:SS.mmm
                        s = float(c.get('timestamp', 0))
                        m = int(s // 60)
                        sec = s % 60
                        ts_str = f"{m:02d}:{sec:06.3f}"
                        
                        latex += f"{ts_str} & {c.get('frame_n','-')} & {c.get('pts','-')} & Corte Visual \\\\ \\hline \n"
                    latex += r"\bottomrule \end{longtable}"
                else:
                    latex += r"\begin{tcolorbox}[colback=success!10,colframe=success,title=Resultado Visual]"
                    latex += r"Nenhuma descontinuidade visual significativa detectada."
                    latex += r"\end{tcolorbox}"

                # Timestamp Analysis (PTS/DTS)
                ts_anomalies = ca.get('timestamp_anomalies', [])
                if ts_anomalies:
                    latex += r"\subsubsection*{Anomalias Temporais (PTS/DTS)}"
                    latex += r"\begin{tcolorbox}[colback=warning!10,title=Erro de Linearidade Detectado]"
                    latex += r"Foram detectadas inconsistências matemáticas nos registros de tempo (PTS/DTS), indicando possível supressão de quadros ou remuxing."
                    latex += r"\end{tcolorbox}"
                    
                    latex += r"\begin{longtable}{l p{10cm}}"
                    latex += r"\toprule \textbf{Timestamp (PTS)} & \textbf{Detalhe da Anomalia} \\ \midrule "
                    latex += r"\endhead "
                    
                    for anomaly in ts_anomalies:
                        ts = anomaly.get('timestamp', 0)
                        try:
                            ts_val = float(ts)
                            ts_str = f"{ts_val:.3f}s"
                        except (TypeError, ValueError):
                            ts_str = str(ts)
                        
                        msg = esc(anomaly.get('message', ''))
                        latex += f"{ts_str} & {msg} \\\\ \\hline \n"
                        
                    latex += r"\bottomrule \end{longtable}"
                
                latex = self._add_refs(latex, "CONTINUITY")


            # --- STRUCTURE ANALYSIS ---
            if 'structure_analysis' in f_analyses and self.config.get('report_structure', True):
                sa = f_analyses['structure_analysis']
                analysis = sa.get('analysis', {})
                atoms = sa.get('atoms', [])
                
                latex += r"\subsection{Análise de Estrutura de Arquivo (Atom Map)}"
                
                conc = esc(analysis.get('conclusion', 'N/A'))
                interp = esc(analysis.get('interpretation', ''))
                
                # Determine color based on conclusion
                # Fast-Start -> Usually edited/web -> Warning? Or just neutral?
                # User said "softwares de edição organizam ... padronizada".
                # Capture is usually mdat first.
                color = "white"
                if "Fast-Start" in conc:
                    color = "warning!5"
                elif "Capture" in conc:
                    color = "success!5"
                
                latex += f"\\begin{{tcolorbox}}[colback={color},colframe=gray,title=Estrutura Física: {conc}]"
                latex += f"{interp}"
                latex += r"\end{tcolorbox}"
                
                # Map Visual
                latex += r"\noindent\textbf{Ordem dos Blocos (Top-Level Atoms):}"
                latex += r"\begin{itemize}"
                for atom in atoms:
                    atype = esc(atom.get('type', '????'))
                    size = atom.get('size', 0)
                    offset = atom.get('offset', 0)
                    
                    atom_descriptions = {
                        'ftyp': r" \textit{(Header)}",
                        'moov': r" \textit{(Index/Metadados)}",
                        'mdat': r" \textit{(Stream de Mídia)}",
                        'free': r" \textit{(Padding)}",
                    }
                    desc = atom_descriptions.get(atype, "")
                    
                    # Highlight critical atoms
                    if atype in ['moov', 'mdat']:
                        latex += f"\\item \\textbf{{\\texttt{[{atype}]}}} (Offset: {offset}, Size: {size} bytes){desc}"
                    else:
                        latex += f"\\item \\texttt{[{atype}]} (Offset: {offset}){desc}"
                latex += r"\end{itemize}"
                
                latex = self._add_refs(latex, "STRUCTURE")

            # --- 6. STATISTICAL COMPRESSION ---
            if 'compression_analysis' in f_analyses and self.config.get('report_statistical', True):
                comp = f_analyses['compression_analysis']
                benford = comp.get('benford_analysis', {})
                fourier = comp.get('fourier_analysis', {})
                conclusion = esc(comp.get('conclusion', ''))
                
                latex += r"\subsection{Análise de Compressão Avançada (Estatística)}"
                
                latex += r"\begin{tcolorbox}[colback=lightgray,title=Objetivo]"
                latex += r"Detectar assinaturas matemáticas de recompressão através da análise dos tamanhos dos quadros (Bitstream Analysis)."
                latex += r"\end{tcolorbox}"
                
                # BENFORD
                latex += r"\subsubsection{Lei de Benford Segmentada (I, P, B)}"
                
                # Educational foundation
                latex += r"\begin{tcolorbox}[colback=lightgray,title=O que é a Lei de Benford?]"
                latex += r"\textbf{Definição:} A Lei de Benford (ou Lei do Primeiro Dígito) é um fenômeno matemático que descreve a distribuição dos primeiros dígitos em conjuntos de dados naturais. "
                latex += r"Em dados não-manipulados, o dígito 1 aparece como primeiro dígito em aproximadamente 30\% dos casos, o 2 em 17.6\%, e assim sucessivamente."
                latex += r"\vspace{0.2cm}"
                latex += r"\textbf{Aplicação em Vídeo Forense:} Analisamos os tamanhos dos quadros de vídeo comprimidos (em bytes). "
                latex += r"Vídeos autênticos tendem a seguir a Lei de Benford. \textbf{Recompressão}, \textbf{edição} ou \textbf{manipulação} alteram os padrões de compressão, "
                latex += r"causando desvios detectáveis na distribuição dos primeiros dígitos."
                latex += r"\end{tcolorbox}"
                
                # Metodologia expandida
                latex += r"\begin{tcolorbox}[colback=white,colframe=secondary,title=Metodologia e Interpretação por Tipo de Quadro]"
                latex += r"\textbf{Segmentação:} A análise é feita separadamente para cada tipo de quadro (I, P, B) e globalmente, pois cada tipo tem características estatísticas distintas."
                latex += r"\vspace{0.2cm}"
                latex += r"\textbf{Interpretação Forense:}"
                latex += r"\begin{itemize}[leftmargin=1cm]"
                latex += r"\item \textbf{Quadros I (Intra):} Desvios indicam \textbf{edição espacial} (crop, resize, overlay, inserção de elementos). I-frames são os mais sensíveis a manipulação visual."
                latex += r"\item \textbf{Quadros P/B (Preditivos):} Anomalias sugerem \textbf{manipulação temporal} (frame dropping, inserção) ou \textbf{recompressão} (alteração da estrutura GOP)."
                latex += r"\item \textbf{Global:} Visão geral da integridade estatística. Combinação dos padrões de todos os tipos de quadro."
                latex += r"\end{itemize}"
                latex += r"\vspace{0.2cm}"
                latex += r"\textbf{Métrica de Divergência:} Calcula-se a distância estatística (divergência KL ou chi-quadrado) entre a distribuição observada e a esperada pela Lei de Benford. "
                latex += r"Quanto maior o score, maior o desvio."
                latex += r"\end{tcolorbox}"
                
                # Reference values table (PRESENTED BEFORE RESULTS)
                latex += r"\vspace{0.3cm}"
                latex += r"\noindent\textbf{Valores de Referência para Divergência:}"
                latex += r"\begin{center}"
                latex += r"\begin{tabular}{l l l}"
                latex += r"\toprule \textbf{Score} & \textbf{Classificação} & \textbf{Interpretação} \\ \midrule "
                latex += r"< 0.05 & \textcolor{success}{\textbf{Excelente}} & Aderência forte à Lei de Benford (vídeo autêntico) \\ "
                latex += r"0.05 - 0.10 & \textcolor{success}{Bom} & Desvio leve, ainda dentro da normalidade \\ "
                latex += r"0.10 - 0.15 & \textcolor{warning}{Moderado} & Desvio suspeito, investigar contexto \\ "
                latex += r"> 0.15 & \textcolor{danger}{\textbf{Alto}} & Forte indício de recompressão ou manipulação \\ "
                latex += r"\bottomrule \end{tabular}"
                latex += r"\end{center}"
                latex += r"\vspace{0.3cm}"

                # Detectar formato (Segmentado vs Legado)
                if 'global' in benford:
                    segments = ['global', 'I', 'P', 'B']
                else:
                    segments = ['global']
                    benford = {'global': benford}
                
                latex += r"\subsubsection*{Resultados Calculados}"
                latex += r"\begin{longtable}{l c l}"
                latex += r"\toprule \textbf{Segmento} & \textbf{Divergência} & \textbf{Status} \\ \midrule "
                
                for seg in segments:
                    b_data = benford.get(seg, {})
                    if not b_data or 'error' in b_data:
                        score_fmt = "N/A"
                        st = "Insuficiente"
                        row_col = ""
                    else:
                        sc = b_data.get('divergence_score', 0)
                        score_fmt = f"{sc:.4f}"
                        st = esc(str(b_data.get('status', 'N/A')))
                        
                        if sc > 0.15:
                            row_col = r"\rowcolor{danger!15}"
                        elif sc > 0.10:
                            row_col = r"\rowcolor{warning!15}"
                        else:
                            row_col = ""
                        
                    seg_name = seg.upper() if seg != 'global' else "GLOBAL"
                    latex += f"{row_col} \\textbf{{{seg_name}}} & {score_fmt} & {st} \\\\ \\hline \n"
                    
                latex += r"\bottomrule \end{longtable}"
                
                # Tabela Detalhada (Global)
                b_global = benford.get('global', {})
                obs = b_global.get('observed_freq', [])
                exp = b_global.get('expected_freq', [])
                
                if obs and len(obs) == 9:
                    latex += r"\subsubsection*{Detalhamento por Dígito (Global)}"
                    latex += r"\noindent\textit{\small Desvios > 5\% destacados em laranja.}"
                    latex += r"\vspace{0.3cm}"
                    latex += r"\begin{center}"
                    latex += r"\begin{tabular}{r r r r}"
                    latex += r"\toprule \textbf{Díc.} & \textbf{Obs.} & \textbf{Esp.} & \textbf{Desvio} \\ \midrule "
                    for i in range(9):
                        o = obs[i]
                        e = exp[i]
                        d = o - e
                        row_color = r"\rowcolor{danger!20}" if abs(d) > 0.05 else ""
                        latex += f"{row_color} {i+1} & {o*100:.1f}\\% & {e*100:.1f}\\% & {d*100:+.1f}\\% \\\\ \n"
                    latex += r"\bottomrule \end{tabular}"
                    latex += r"\end{center}"
                    latex += r"\vspace{0.3cm}"
                
                latex = self._add_refs(latex, "BENFORD_VIDEO")

                # FOURIER
                f_status = esc(fourier.get('status', 'N/A'))
                f_period = fourier.get('dominant_period_frames', 0)
                f_strength = fourier.get('peak_strength', 0)
                
                latex += r"\subsubsection{Análise de Periodicidade (Estrutura GOP)}"
                
                # Educational foundation
                latex += r"\begin{tcolorbox}[colback=lightgray,title=O que é Análise de Periodicidade?]"
                latex += r"\textbf{Conceito:} Utiliza a Transformada Rápida de Fourier (FFT) para detectar padrões repetitivos nos tamanhos dos quadros ao longo do tempo. "
                latex += r"Vídeos comprimidos exibem uma 'pulsação' característica devido à estrutura GOP."
                latex += r"\vspace{0.2cm}"
                latex += r"\textbf{Detecção de GOP:} I-frames são muito maiores que P/B-frames, criando um padrão periódico detectável. "
                latex += r"A FFT identifica a frequência dominante dessa pulsação, revelando o tamanho do GOP usado na compressão."
                latex += r"\end{tcolorbox}"
                
                # Forensic interpretation
                latex += r"\begin{tcolorbox}[colback=white,colframe=secondary,title=Interpretação Forense]"
                latex += r"\textbf{GOPs Fixos vs. Variáveis:}"
                latex += r"\begin{itemize}[leftmargin=1cm]"
                latex += r"\item \textbf{GOP Fixo + Alto Peak Strength:} Padrão rígido e uniforme. Comum em \textbf{software de edição profissional}, \textbf{streaming}, ou \textbf{transcodificação}. Indica possível re-encoding."
                latex += r"\item \textbf{GOP Variável + Baixo Peak Strength:} Padrão adaptativo. Típico de \textbf{gravação direta de câmeras/smartphones} modernos que ajustam GOP conforme cena (motion-adaptive)."
                latex += r"\end{itemize}"
                latex += r"\vspace{0.2cm}"
                latex += r"\textbf{Dupla Compressão:} Se o período detectado difere do GOP observado nos metadados, pode indicar que o vídeo foi recomprimido com parâmetros diferentes."
                latex += r"\end{tcolorbox}"
                
                # Reference values (PRESENTED BEFORE RESULTS)
                latex += r"\vspace{0.3cm}"
                latex += r"\noindent\textbf{Valores de Referência - Força do Pico (Peak Strength):}"
                latex += r"\begin{center}"
                latex += r"\begin{tabular}{l l l}"
                latex += r"\toprule \textbf{Peak Strength} & \textbf{Padrão} & \textbf{Origem Típica} \\ \midrule "
                latex += r"< 1.5 & \textcolor{success}{Fraco/Ausente} & Gravação direta (GOP adaptativo) \\ "
                latex += r"1.5 - 3.0 & \textcolor{success}{Moderado} & Captura com GOP semi-fixo \\ "
                latex += r"3.0 - 5.0 & \textcolor{warning}{Forte} & Re-encoding ou edição \\ "
                latex += r"> 5.0 & \textcolor{danger}{Muito Forte} & Streaming ou software profissional \\ "
                latex += r"\bottomrule \end{tabular}"
                latex += r"\end{center}"
                latex += r"\vspace{0.3cm}"

                # Results table with interpretations
                latex += r"\subsubsection*{Resultados Calculados}"
                latex += r"\begin{longtable}{p{6cm} p{4cm} p{5cm}}"
                latex += r"\toprule \textbf{Métrica} & \textbf{Valor} & \textbf{Interpretação} \\ \midrule "
                
                # Period
                period_interp = ""
                if f_period > 0:
                    if f_period < 10:
                        period_interp = r"Muito curto (provável edição)"
                    elif f_period <= 30:
                        period_interp = r"Padrão (captura direta)"
                    elif f_period <= 120:
                        period_interp = r"Longo (típico de transcodificação)"
                    else:
                        period_interp = r"Extremo (streaming/low bitrate)"
                else:
                    period_interp = r"Não detectado"
                
                latex += f"Periodicidade Detectada & {f_period:.1f} frames & {period_interp} \\\\ \\hline \n"
                
                # Strength with color coding
                strength_interp = ""
                strength_color = ""
                if f_strength > 5.0:
                    strength_interp = r"Muito forte - GOP \textbf{fixo}"
                    strength_color = r"\textcolor{danger}"
                elif f_strength > 3.0:
                    strength_interp = r"Forte - GOP rígido"
                    strength_color = r"\textcolor{warning}"
                elif f_strength > 1.5:
                    strength_interp = r"Moderado - GOP semi-variável"
                    strength_color = r"\textcolor{success}"
                else:
                    strength_interp = r"Fraco - GOP adaptativo"
                    strength_color = r"\textcolor{success}"
                
                latex += f"Força do Padrão (Peak) & {strength_color}{{{f_strength:.2f}}} & {strength_interp} \\\\ \\hline \n"
                latex += f"Diagnóstico Geral & \\multicolumn{{2}}{{l}}{{{f_status}}} \\\\ \\hline \n"
                latex += r"\bottomrule \end{longtable}"
                
                if conclusion:
                    is_suspicious = "viola" in conclusion or "rígida" in conclusion or f_strength > 5.0
                    bg_conc = "danger!10" if is_suspicious else "success!10"
                    
                    latex += r"\subsection*{Conclusão e Diagnóstico Estatístico}"
                    latex += r"\begin{tcolorbox}[colback=" + bg_conc + r", title=Síntese da Análise de Compressão]"
                    
                    # Elaborar conclusão mais detalhada
                    refined_conc = conclusion
                    if is_suspicious:
                        refined_conc += r" \textbf{ALERTA:} A rigidez e os desvios estatísticos detectados são incompatíveis com uma gravação direta de câmera, sugerindo fortemente que o arquivo passou por transcodificação e/ou manipulação temporal."
                    else:
                        refined_conc += r" Os padrões detectados são consistentes com o comportamento esperado de câmeras comerciais e não apresentam anomalias típicas de reprocessamento agressivo."
                        
                    latex += refined_conc
                    latex += r"\end{tcolorbox}"
                
                latex = self._add_refs(latex, "PERIODICITY")

            # --- 7. IMAGE ANALYSIS (ELA) ---
            if 'image_analysis' in f_analyses and self.config.get('report_ela', True):
                img_an = f_analyses['image_analysis']
                meta = img_an.get('metadata', {})
                ela = img_an.get('ela_analysis', {})
                img_hash = img_an.get('file_hash', 'N/A')
                prnu_img = img_an.get('prnu_analysis', {})
                
                latex += r"\subsection{Metadados da Imagem}"
                latex += r"\begin{tcolorbox}[colback=white,colframe=gray]"
                # Use \url for safe wrapping using xurl package
                latex += r"\textbf{SHA-512:} \blackurl{" + str(img_hash) + r"}"
                latex += r"\end{tcolorbox}"
                
                # PRNU Status for Image
                if prnu_img.get('status') == 'extracted':
                    latex += r"\begin{tcolorbox}[colback=success!10,title=Identificação de Fonte (PRNU)]"
                    latex += r"Fingerprint extraído com sucesso. Disponível para comparação cruzada na Matriz de Similaridade."
                    latex += r"\end{tcolorbox}"
                else:
                    latex += r"\begin{tcolorbox}[colback=warning!10,title=Identificação de Fonte (PRNU)]"
                    latex += f"Não foi possível extrair fingerprint: {esc(prnu_img.get('error', 'N/A'))}"
                    latex += r"\end{tcolorbox}"
                
                # Metadata Table
                fmt = meta.get('format', {})
                streams = meta.get('streams', [])
                video_stream = next((s for s in streams if s.get('codec_type') == 'video'), {})
                
                # --- Informações Técnicas ---
                latex += r"\subsubsection*{Informações Técnicas}"
                latex += r"\begin{longtable}{p{6cm} p{9cm}}"
                latex += r"\toprule \textbf{Propriedade} & \textbf{Valor} \\ \midrule "
                latex += r"\endhead "
                
                # Dimensões (Resolution)
                w = video_stream.get('width')
                h = video_stream.get('height')
                if w and h:
                    mp = (w * h) / 1_000_000
                    latex += f"\\textbf{{Resolução}} & {w} x {h} ({mp:.1f} Megapixels) \\\\ \\hline \n"
                
                # Basics
                f_size = fmt.get('size', '0')
                try:
                    f_size_mb = float(f_size) / (1024*1024)
                    latex += f"\\textbf{{Tamanho do Arquivo}} & {f_size_mb:.2f} MB \\\\ \\hline \n"
                except (TypeError, ValueError):
                    latex += f"\\textbf{{Tamanho do Arquivo}} & {esc(str(f_size))} bytes \\\\ \\hline \n"
                    
                latex += f"\\textbf{{Formato Container}} & {esc(fmt.get('format_name', 'N/A'))} \\\\ \\hline \n"
                latex += f"\\textbf{{Codec de Compressão}} & {esc(video_stream.get('codec_name', 'N/A').upper())} \\\\ \\hline \n"
                latex += f"\\textbf{{Pixel Format}} & {esc(video_stream.get('pix_fmt', 'N/A'))} \\\\ \\hline \n"
                
                # Color details if available
                if 'color_space' in video_stream:
                     latex += f"\\textbf{{Espaço de Cor}} & {esc(video_stream.get('color_space'))} \\\\ \\hline \n"
                
                latex += r"\bottomrule \end{longtable}"

                # --- EXIF & Tags ---
                tags = fmt.get('tags', {})
                # Merge with stream tags if any
                if 'tags' in video_stream:
                    tags.update(video_stream['tags'])
                
                # Filter interesting EXIF keys
                exif_keys = [
                    'make', 'model', 'software', 'datetime', 'date', 'creation_time', 
                    'iso', 'exposure', 'shutter', 'aperture', 'fnumber', 'focal_length',
                    'gps', 'latitude', 'longitude', 'artist', 'copyright', 'host_computer'
                ]
                
                found_exif = {}
                for k, v in tags.items():
                    k_lower = k.lower()
                    # Check if key contains any of the interest terms
                    if any(x in k_lower for x in exif_keys):
                        found_exif[k] = v
                
                if found_exif:
                    latex += r"\subsubsection*{Metadados de Câmera (EXIF)}"
                    latex += r"\begin{longtable}{p{6cm} p{9cm}}"
                    latex += r"\toprule \textbf{Tag} & \textbf{Dado Extraído} \\ \midrule "
                    latex += r"\endhead "
                    
                    for k, v in found_exif.items():
                        # Highlight 'software' as it indicates editing
                        val_str = esc(str(v))
                        if 'software' in k.lower() and ('adobe' in val_str.lower() or 'gimp' in val_str.lower() or 'photoshop' in val_str.lower()):
                            row_color = r"\rowcolor{warning!20}"
                        else:
                            row_color = ""
                            
                        latex += f"{row_color} \\textbf{{{esc(k)}}} & {val_str} \\\\ \\hline \n"
                        
                    latex += r"\bottomrule \end{longtable}"
                else:
                    latex += r"\begin{tcolorbox}[colback=lightgray,title=Metadados EXIF]"
                    latex += r"Nenhum metadado de câmera (EXIF) significativo foi encontrado. Isso pode indicar que o arquivo foi processado 'limpo' ou é nativamente digital sem sensores."
                    latex += r"\end{tcolorbox}"

                latex += r"\subsection{Análise de Nível de Erro (ELA)}"
                
                latex += r"\begin{tcolorbox}[colback=lightgray,title=Fundamentação Científica (Steady State)]"
                latex += r"A Error Level Analysis (ELA) baseia-se no princípio de que imagens JPEG, quando salvas sequencialmente com o mesmo nível de qualidade, atingem um estado de equilíbrio (steady state). "
                latex += r"Modificações posteriores à última compressão resetam este estado. Assim, ao recomprimir a imagem e medir o erro (Global Difference Score), regiões manipuladas apresentam níveis de ruído divergentes do restante da imagem."
                latex += r"\end{tcolorbox}"
                if ela.get('status') == 'success':
                    ela_score = ela.get('ela_score', 0)
                    ela_img_file = ela.get('ela_image')
                    amp = ela.get('amplification_factor', 15)
                    
                    latex += f"\\textbf{{Score de Diferença Global (MAE):}} {ela_score:.2f} (Amplificação Visual: {amp}x)\n\n"
                    
                    # Tabela de Referência ELA
                    latex += r"\noindent\textbf{Parâmetros de Interpretação (Valores MAE):}"
                    latex += r"\begin{center}"
                    latex += r"\begin{tabular}{l l l}"
                    latex += r"\toprule \textbf{Score MAE} & \textbf{Classificação} & \textbf{Interpretação Forense} \\ \midrule "
                    latex += r"< 2.0 & \textcolor{success}{Muito Baixo} & Alta qualidade / Steady State (Q95-100) \\ "
                    latex += r"2.0 - 5.0 & \textcolor{success}{Típico} & Padrão esperado para JPEG (Q80-95) \\ "
                    latex += r"5.0 - 10.0 & \textcolor{warning}{Elevado} & Recompressão ou múltiplos salvamentos \\ "
                    latex += r"> 10.0 & \textcolor{danger}{Crítico} & Compressão agressiva / Manipulação profunda \\ "
                    latex += r"\bottomrule \end{tabular}"
                    latex += r"\end{center}"
                    
                    latex += r"\vspace{0.3cm}"
                    
                    # Embed Image
                    # No LaTeX, precisamos do caminho relativo ao .tex ou absoluto.
                    # O .tex está em report/, imagem em results/.
                    # Path relativo: ../results/filename
                    # Mas o código python roda _compile_latex com cwd=report_dir
                    # Então references devem ser relative to report_dir.
                    # As imagens estão em ../results
                    
                    # Precisamos garantir que o filename seja seguro
                    if ela_img_file:
                        # Latex graphics path trickery usually needs full path or relative.
                        # Vamos usar relative path: ../results/filename
                        # Mas windows paths com backslash quebram latex. Usar forward slash.
                        rel_path = f"../results/{ela_img_file}"
                        
                        latex += r"\begin{figure}[H]"
                        latex += r"\centering"
                        latex += f"\\includegraphics[width=0.8\\textwidth]{{{rel_path}}}"
                        latex += r"\caption{Mapa de Calor ELA}"
                        latex += r"\end{figure}"
                        
                        latex += r"\begin{tcolorbox}[colback=white,colframe=primary,title=Interpretação]"
                        latex += esc(ela.get('interpretation', ''))
                        latex += r"\end{tcolorbox}"
                else:
                    latex += esc(ela.get('error', 'Unknown Error'))
                    latex += r"\end{tcolorbox}"
                
                latex = self._add_refs(latex, "ELA")


            # --- NOISE CONSISTENCY ---
            # Check if it was part of image_analysis OR standalone
            noise_data = None
            if 'image_analysis' in f_analyses:
                noise_data = f_analyses['image_analysis'].get('noise_analysis')
            elif 'noise_analysis' in f_analyses:
                noise_data = f_analyses['noise_analysis']

            if noise_data and self.config.get('report_noise', True):
                noise = noise_data
                stats = noise.get('global_stats', {})
                outliers = noise.get('outliers_detected', 0)
                map_file = noise.get('map_image')
                
                latex += r"\subsection{Análise de Consistência de Ruído (Análise de Erro de Nível)}"
                
                latex += r"\begin{tcolorbox}[colback=lightgray,title=Metodologia Forense]"
                latex += r"\textbf{Princípio:} Sensores de câmeras digitais imprimem um padrão de ruído estatisticamente uniforme em toda a imagem (PRNU e ruído térmico). Quando uma imagem é manipulada via \textit{splicing} (colagem) ou geração por IA, a região alterada herda características de ruído diferentes da cena original."
                latex += r"\vspace{0.2cm}"
                latex += r"\\ \textbf{Procedimento:} A imagem é segmentada em blocos de 64x64 pixels. Para cada bloco, extraímos o resíduo de ruído e calculamos:"
                latex += r"\begin{itemize}[leftmargin=1cm]"
                latex += r"\item \textbf{Variância do Ruído:} Mede a intensidade da flutuação aleatória. Desvios indicam áreas provenientes de sensores distintos ou processos sintéticos."
                latex += r"\item \textbf{Entropia de Shannon:} Avalia a complexidade da informação no ruído. Regiões suavizadas por IA ou filtros apresentam entropia anormalmente baixa."
                latex += r"\item \textbf{Detecção de Outliers:} Blocos com variância superior a 3 desvios padrões (3\sigma) da média global são sinalizados como pontos de interesse pericial."
                latex += r"\end{itemize}"
                latex += r"\end{tcolorbox}"
                
                if noise.get('status') == 'success':
                    # Global Statistics
                    latex += r"\noindent\textbf{Estatísticas Globais de Ruído:}"
                    latex += r"\begin{itemize}"
                    latex += f"\\item \\textbf{{Variância Média:}} {stats.get('mean_variance',0):.2f}"
                    latex += f"\\item \\textbf{{Desvio Padrão (Inter-blocos):}} {stats.get('std_variance',0):.2f}"
                    latex += f"\\item \\textbf{{Entropia Média do Resíduo:}} {stats.get('mean_entropy',0):.3f}"
                    latex += f"\\item \\textbf{{Blocos Anômalos (Desvios Críticos):}} {outliers} detectados."
                    latex += r"\end{itemize}"
                    
                    # Heatmap
                    if map_file:
                        rel_path = f"../results/{map_file}"
                        latex += r"\begin{figure}[H]"
                        latex += r"\centering"
                        latex += f"\\includegraphics[width=0.85\\textwidth]{{{rel_path}}}"
                        latex += r"\caption{Mapa de Distribuição de Ruído (Analítico de Variância) - JET Colormap}"
                        latex += r"\end{figure}"
                        
                    # Conclusion
                    if outliers > 0:
                        latex += r"\begin{tcolorbox}[colback=warning!10,colframe=warning,title=Alerta de Inconsistência Física]"
                        latex += r"Foram detectadas regiões com assinaturas de ruído estatisticamente divergentes do corpo principal da imagem. "
                        latex += r"Conforme o mapa pericial, as áreas com cores nos extremos (Azul Profundo ou Vermelho Intenso) indicam quebra da homogeneidade do sensor, sugerindo manipulação localizada por colagem ou reconstrução sintética."
                        latex += r"\end{tcolorbox}"
                    else:
                        latex += r"\begin{tcolorbox}[colback=success!10,colframe=success,title=Análise de Homogeneidade]"
                        latex += r"A distribuição de ruído apresenta-se estatisticamente uniforme em toda a extensão do arquivo analisado. Não foram encontrados desvios significativos que indiquem a inserção de elementos externos ou processamento localizado diferenciado."
                        latex += r"\end{tcolorbox}"
                else:
                     latex += r"\textrm{Erro na análise de ruído: " + esc(noise.get('error','')) + r"}"
                
                latex = self._add_refs(latex, "NOISE")

            # --- 8. DEEPFAKE ANALYSIS ---
            deepfake_data = f_analyses.get('deepfake_analysis')
            if not deepfake_data:
                for k, v in f_analyses.items():
                    if str(k).endswith('deepfake_analysis'):
                        deepfake_data = v
                        break
            
            if deepfake_data and deepfake_data.get('status') not in ['error', 'skipped'] and self.config.get('report_deepfake', True):
                df = deepfake_data
                
                latex += r"\subsection{Detecção de Mídias Sintéticas e Deepfakes}"
                
                latex += r"\begin{tcolorbox}[colback=lightgray,title=Fundamentação Forense e Procedimentos]"
                latex += r"\textbf{O que é Deepfake?} Trata-se de mídias geradas por algoritmos de inteligência artificial (GANs e Modelos de Difusão) que podem replicar ou alterar faces, vozes e ambientes com alta verossimilhança. "
                latex += r"\vspace{0.2cm}"
                latex += r"\\ \textbf{Procedimentos de Verificação:} Implementamos quatro camadas de análise para detectar falhas microscópicas inerentes ao processo de síntese:"
                latex += r"\begin{itemize}[leftmargin=1cm]"
                latex += r"\item \textbf{Análise Espectral Multi-canal (FFT):} Modelos generativos criam frequências repetitivas (artefatos de amostragem) que se manifestam como 'picos de energia' no espectro de Fourier. Analisamos não apenas a luminância (Y), mas também a crominância (Cb e Cr), onde modelos modernos costumam deixar rastros mais evidentes."
                latex += r"\item \textbf{Texture Analysis Multi-escala (LBP):} A pele humana real possui micro-irregularidades estocásticas. Algoritmos de IA tendem a produzir texturas com repetitividade matemática ou suavização excessiva, identificadas via padrões binários locais (LBP) em múltiplas resoluções."
                latex += r"\item \textbf{Divergência de Consistência Física:} Avalia se a face detém as mesmas propriedades físicas de ruído do cenário de fundo. Deepfakes frequentemente apresentam uma face de alta qualidade inserida em um fundo de baixa fidelidade, gerando uma 'assinatura de ruído dupla'."
                latex += r"\item \textbf{Instabilidade Temporal (Deepfake Jitter):} Em vídeos, a inconsistência na geração frame-a-frame causa micro-tremores ou variações bruscas de textura que não ocorrem em gravações contínuas autênticas."
                latex += r"\end{itemize}"
                latex += r"\end{tcolorbox}"
                
                
                # Detection summary
                faces = df.get('detected_faces', 0)
                bodies = df.get('detected_bodies', 0)
                is_suspicious = df.get('is_suspicious', False)
                
                latex += r"\vspace{0.3cm}"
                latex += r"\noindent\textbf{Detecção de Elementos Humanos:}"
                latex += r"\begin{itemize}[leftmargin=1cm]"
                latex += f"\\item Faces detectadas: {faces}"
                latex += f"\\item Corpos/silhuetas detectados: {bodies}"
                latex += r"\end{itemize}"
                
                if faces == 0 and bodies == 0:
                    latex += r"\begin{tcolorbox}[colback=warning!10,title=Nota sobre Detecção Automática]"
                    latex += r"Nenhum rosto ou corpo humano foi detectado automaticamente. No entanto, as técnicas de análise espectral e de textura aplicadas abaixo podem identificar artefatos de geração sintética (IA/GAN) em qualquer região da mídia (cenários, objetos ou fundo), independentemente da presença humana."
                    latex += r"\end{tcolorbox}"
                
                # Results table with color-coded interpretation
                latex += r"\subsubsection*{Resultados da Análise}"
                latex += r"\begin{longtable}{p{5cm} p{3cm} p{2.5cm} p{5cm}}"
                latex += r"\toprule \textbf{Métrica} & \textbf{Score} & \textbf{Status} & \textbf{Interpretação} \\ \midrule "
                latex += r"\endhead "
                
                # Consistency Score
                cons_score = df.get('consistency_score', 0)
                cons_status, cons_color, cons_interp = "", "", ""
                if cons_score < 30:
                    cons_status = "Baixo"
                    cons_color = r"\textcolor{success}"
                    cons_interp = "Consistente com mídia autêntica"
                elif cons_score < 70:
                    cons_status = "Moderado"
                    cons_color = r"\textcolor{warning}"
                    cons_interp = "Zona ambígua"
                else:
                    cons_status = "Alto"
                    cons_color = r"\textcolor{danger}"
                    cons_interp = "Descontinuidades suspeitas"
                
                latex += f"Consistência Física & {cons_color}{{{cons_score}}} & {cons_status} & {cons_interp} \\\\ \\hline \n"
                
                # Frequency Score (GAN artifacts)
                freq_score = df.get('frequency_score', 0)
                freq_status, freq_color, freq_interp = "", "", ""
                if freq_score < 30:
                    freq_status = "Baixo"
                    freq_color = r"\textcolor{success}"
                    freq_interp = "Espectro natural"
                elif freq_score < 70:
                    freq_status = "Moderado"
                    freq_color = r"\textcolor{warning}"
                    freq_interp = "Artefatos leves"
                else:
                    freq_status = "Alto"
                    freq_color = r"\textcolor{danger}"
                    freq_interp = "Padrões típicos de GAN"
                
                latex += f"Artefatos GAN (FFT) & {freq_color}{{{freq_score}}} & {freq_status} & {freq_interp} \\\\ \\hline \n"
                
                # Texture Score
                tex_score = df.get('texture_score', 0)
                tex_status, tex_color, tex_interp = "", "", ""
                if tex_score < 30:
                    tex_status = "Baixo"
                    tex_color = r"\textcolor{success}"
                    tex_interp = "Textura natural"
                elif tex_score < 70:
                    tex_status = "Moderado"
                    tex_color = r"\textcolor{warning}"
                    tex_interp = "Textura ligeiramente artificial"
                else:
                    tex_status = "Alto"
                    tex_color = r"\textcolor{danger}"
                    tex_interp = "Textura sintética"
                
                latex += f"Textura Facial (LBP) & {tex_color}{{{tex_score}}} & {tex_status} & {tex_interp} \\\\ \\hline \n"
                
                # Temporal Jitter (only for videos)
                if df.get('type') == 'video':
                    jitter = df.get('temporal_jitter', 0)
                    jitter_status, jitter_color, jitter_interp = "", "", ""
                    if jitter < 10:
                        jitter_status = "Baixo"
                        jitter_color = r"\textcolor{success}"
                        jitter_interp = "Estável"
                    elif jitter < 20:
                        jitter_status = "Moderado"
                        jitter_color = r"\textcolor{warning}"
                        jitter_interp = "Instabilidade leve"
                    else:
                        jitter_status = "Alto"
                        jitter_color = r"\textcolor{danger}"
                        jitter_interp = "Instabilidade alta (típico de deepfake)"
                    
                    latex += f"Jitter Temporal & {jitter_color}{{{jitter}}} & {jitter_status} & {jitter_interp} \\\\ \\hline \n"
                
                latex += r"\bottomrule \end{longtable}"
                
                # Overall conclusion
                latex += r"\subsubsection*{Diagnóstico Geral}"
                if is_suspicious:
                    latex += r"\begin{tcolorbox}[colback=danger!10,colframe=danger,title=\textbf{ALERTA: Mídia Suspeita}]"
                    latex += r"Um ou mais indicadores atingiram níveis críticos. \textbf{Recomenda-se análise humana especializada.}"
                    latex += r"\vspace{0.2cm}"
                    latex += r"\\"
                    latex += r"\textbf{Detalhes dos Alertas:}"
                    latex += r"\begin{itemize}[leftmargin=1cm]"
                    for detail in df.get('details', []):
                        latex += f"\\item {esc(detail)}"
                    latex += r"\end{itemize}"
                    latex += r"\end{tcolorbox}"
                else:
                    latex += r"\begin{tcolorbox}[colback=success!10,colframe=success,title=Mídia Aparentemente Autêntica]"
                    latex += r"Nenhum indicador crítico de síntese artificial foi detectado. Scores estão dentro de parâmetros esperados para mídia autêntica ou comprimida."
                    latex += r"\end{tcolorbox}"
                
                latex += r"\vspace{0.3cm}"
                latex += r"\noindent\textbf{Tabela de Referência - Interpretação dos Scores:}"
                latex += r"\begin{center}"
                latex += r"\begin{tabular}{l l l}"
                latex += r"\toprule \textbf{Faixa de Score} & \textbf{Status} & \textbf{Interpretação Forense} \\ \midrule "
                latex += r"0 - 30 & \textcolor{success}{\textbf{Baixo}} & Consistente com mídia autêntica \\ "
                latex += r"30 - 50 & \textcolor{warning}{Moderado-Baixo} & Zona de transição, monitorar outros scores \\ "
                latex += r"50 - 70 & \textcolor{warning}{Moderado-Alto} & Suspeito, investigar contexto \\ "
                latex += r"> 70 & \textcolor{danger}{\textbf{Alto}} & Forte indício de deepfake ou manipulação \\ "
                latex += r"\bottomrule \end{tabular}"
                latex += r"\end{center}"
                latex += r"\vspace{0.1cm}"
                latex += r"\noindent\textit{\small \textbf{Importante:} Esta análise é probabilística (heurística), não determinística. Resultados devem ser contextualizados com outras evidências.}"
                latex += r"\vspace{0.3cm}"
                
                latex = self._add_refs(latex, "DEEPFAKE")


            # --- DCT ANALYSIS (FREQUENCY) ---
            dct_data = None
            if 'image_analysis' in f_analyses:
                dct_data = f_analyses['image_analysis'].get('dct_analysis')
            elif 'dct_analysis' in f_analyses:
                dct_data = f_analyses['dct_analysis']
                
            if dct_data and self.config.get('report_ela', True): # Usando report_ela para DCT também ou report_metadata?
                dct = dct_data
                d_stats = dct.get('global_stats', {})
                d_map = dct.get('map_image')
                d_conc = dct.get('conclusion', '')
                
                latex += r"\subsection{Análise de Frequência (DCT)}"
                
                latex += r"\begin{tcolorbox}[colback=lightgray,title=Metodologia]"
                latex += r"Analisa os coeficientes da Transformada Discreta de Cosseno (DCT) em blocos de 8x8. O mapa de calor representa a energia de alta frequência (textura/detalhe). Descontinuidades abruptas podem indicar manipulação."
                latex += r"\end{tcolorbox}"
                
                if dct.get('status') == 'success':
                    # Heatmap
                    if d_map:
                        rel_path = f"../results/{d_map}"
                        latex += r"\begin{figure}[H]"
                        latex += r"\centering"
                        latex += f"\\includegraphics[width=0.85\\textwidth]{{{rel_path}}}"
                        latex += r"\caption{Mapa de Energia AC (DCT) - INFERNO Colormap}"
                        latex += r"\end{figure}"
                        
                    # Stats and Conclusion
                    latex += r"\noindent\textbf{Métricas de Energia:}"
                    latex += r"\begin{itemize}"
                    latex += f"\\item \\textbf{{Energia Média AC:}} {d_stats.get('mean_ac_energy',0):.2f}"
                    latex += f"\\item \\textbf{{Desvio Padrão:}} {d_stats.get('std_ac_energy',0):.2f}"
                    latex += r"\end{itemize}"
                    
                    latex += r"\begin{tcolorbox}[colback=white,colframe=primary,title=Conclusão DCT]"
                    latex += esc(d_conc)
                    latex += r"\end{tcolorbox}"
                else:
                    latex += esc(dct.get('error', 'Unknown Error'))
                    latex += r"\end{tcolorbox}"

                latex = self._add_refs(latex, "DCT")


            # --- COPY-MOVE ANALYSIS ---
            cm_data = None
            if 'image_analysis' in f_analyses:
                cm_data = f_analyses['image_analysis'].get('copymove_analysis')
            elif 'copymove_analysis' in f_analyses:
                cm_data = f_analyses['copymove_analysis']
                
            if cm_data and self.config.get('report_copymove', True):
                cm = cm_data
                matches = cm.get('matches_found', 0)
                cm_map = cm.get('map_image')
                cm_conc = cm.get('conclusion', '')
                
                latex += r"\subsection{Detecção de Clonagem (Copy-Move)}"
                latex += r"\begin{tcolorbox}[colback=lightgray,title=Metodologia]"
                latex += r"Utiliza algoritmos de correspondência de características (SIFT) para encontrar regiões idênticas duplicadas na imagem. As linhas coloridas conectam os pontos de origem e destino da cópia."
                latex += r"\end{tcolorbox}"
                
                if cm.get('status') == 'success':
                    if cm_map and matches > 0:
                        rel_path = f"../results/{cm_map}"
                        latex += r"\begin{figure}[H]"
                        latex += r"\centering"
                        latex += f"\\includegraphics[width=0.85\\textwidth]{{{rel_path}}}"
                        latex += r"\caption{Visualização de Clonagem (Matches SIFT)}"
                        latex += r"\end{figure}"
                        
                    latex += r"\noindent\textbf{Resultados:}"
                    latex += r"\begin{itemize}"
                    latex += f"\\item \\textbf{{Links Encontrados:}} {matches} pares de pontos idênticos."
                    latex += r"\end{itemize}"
                    
                    if matches > 10:
                        box_col = "danger!10"
                        title = "ALERTA DE CLONAGEM"
                    elif matches > 0:
                        box_col = "warning!10"
                        title = "Pontos Suspeitos"
                    else:
                         box_col = "success!10"
                         title = "Negativo"
                         
                    latex += f"\\begin{{tcolorbox}}[colback={box_col},title={title}]"
                    latex += esc(cm_conc)
                    latex += r"\end{tcolorbox}"
                else:
                    latex += r"\textrm{Erro Copy-Move: " + esc(cm.get('error','')) + r"}"
                
                latex = self._add_refs(latex, "COPYMOVE")



            # --- RESAMPLING ANALYSIS (INTERPOLATION) ---
            res_data = None
            if 'image_analysis' in f_analyses:
                res_data = f_analyses['image_analysis'].get('resampling_analysis')
            elif 'resampling_analysis' in f_analyses:
                res_data = f_analyses['resampling_analysis']
                
            if res_data and self.config.get('report_resampling', True):
                res = res_data
                res_map = res.get('map_image')
                res_score = res.get('global_periodicity_score', 0)
                res_conc = res.get('conclusion', '')
                
                latex += r"\subsection{Detecção de Resampling (Interpolação)}"
                latex += r"\begin{tcolorbox}[colback=lightgray,title=Metodologia]"
                latex += r"Analisa a periodicidade dos pixels vizinhos (via FFT) para detectar traços de redimensionamento ou rotação. Áreas vermelhas no mapa indicam forte correlação periódica (provável manipulação geométrica)."
                latex += r"\end{tcolorbox}"
                
                if res.get('status') == 'success':
                    if res_map:
                        rel_path = f"../results/{res_map}"
                        latex += r"\begin{figure}[H]"
                        latex += r"\centering"
                        latex += f"\\includegraphics[width=0.85\\textwidth]{{{rel_path}}}"
                        latex += r"\caption{Mapa de Probabilidade de Resampling}"
                        latex += r"\end{figure}"
                        
                    latex += r"\noindent\textbf{Métricas Espectrais:}"
                    latex += r"\begin{itemize}"
                    latex += f"\\item \\textbf{{Periodicidade Global:}} {res_score:.2f} (Pico/Média)"
                    latex += r"\end{itemize}"
                    
                    # Color coding conclusion
                    if "ALTA PROBABILIDADE" in res_conc.upper():
                        box_col = "danger!10"
                    elif "Indícios" in res_conc:
                        box_col = "warning!10"
                    else:
                        box_col = "success!10"

                    latex += f"\\begin{{tcolorbox}}[colback={box_col},title=Conclusão Resampling]"
                    latex += esc(res_conc)
                    latex += r"\end{tcolorbox}"
                else:
                    latex += r"\textrm{Erro Resampling: " + esc(res.get('error','')) + r"}"
                
                latex = self._add_refs(latex, "RESAMPLING")


            # --- JPEG COMPRESSION ANALYSIS (GHOSTS) ---
            jpeg_data = None
            if 'image_analysis' in f_analyses:
                jpeg_data = f_analyses['image_analysis'].get('jpeg_analysis')
            elif 'jpeg_analysis' in f_analyses:
                jpeg_data = f_analyses['jpeg_analysis']
                
            if jpeg_data and self.config.get('report_jpeg_ghosts', True):
                jpg = jpeg_data
                ghost_map = jpg.get('map_image')
                is_double = jpg.get('is_double_compression', False)
                est_q = jpg.get('estimated_quality', 0)
                jpg_conc = jpg.get('conclusion', '')
                
                latex += r"\subsection{Análise de Compressão JPEG (Ghosts)}"
                latex += r"\begin{tcolorbox}[colback=lightgray,title=Metodologia e Conceitos Fundamentais]"
                latex += r"\textbf{Princípio:} Identifica inconsistências de compressão comparando a imagem com versões recomprimidas em diversas qualidades. "
                latex += r"Se a imagem foi editada e re-salva, ela retém 'fantasmas' (artefatos) da compressão anterior."
                latex += r"\vspace{0.2cm}"
                latex += r"\textbf{O que é o Fator Q (Quality Factor)?} É o parâmetro que define a agressividade da compressão JPEG (geralmente de 1 a 100). "
                latex += r"Quanto maior o Q, maior a fidelidade e menor a perda de dados."
                latex += r"\vspace{0.2cm}"
                latex += r"\textbf{Qualidade Original Estimada:} Através de um 'sweep' de recompressão, o sistema busca o ponto onde o erro residual é mínimo. "
                latex += r"Um mínimo local em um valor Q específico (ex: Q63) sugere fortemente que a imagem passou por um ciclo de compressão naquela qualidade no passado."
                latex += r"\end{tcolorbox}"
                
                if jpg.get('status') == 'success':
                    if ghost_map:
                        rel_path = f"../results/{ghost_map}"
                        latex += r"\begin{figure}[H]"
                        latex += r"\centering"
                        latex += f"\\includegraphics[width=0.85\\textwidth]{{{rel_path}}}"
                        latex += r"\caption{Ghost Map (Diferença para Q" + str(est_q) + r")}"
                        latex += r"\end{figure}"
                        
                    latex += r"\noindent\textbf{Resultados da Investigação:}"
                    latex += r"\begin{itemize}"
                    
                    status_fmt = r"\textbf{Dupla Compressão / Edição Detectada}" if is_double else "Padrão único/Consistente"
                    latex += f"\\item \\textbf{{Diagnóstico:}} {status_fmt}"
                    
                    if est_q > 0:
                        latex += f"\\item \\textbf{{Fator Q de Referência:}} Q{est_q} (Ponto de menor erro detectado)"
                    latex += r"\end{itemize}"
                    
                    box_col = "danger!10" if is_double else "success!10"
                    title = "Conclusão da Análise de Ghosts"

                    latex += f"\\begin{{tcolorbox}}[colback={box_col},title={title}]"
                    latex += esc(jpg_conc)
                    latex += r"\end{tcolorbox}"
                else:
                    latex += r"\textrm{Erro na análise JPEG: " + esc(jpg.get('error','')) + r"}"
                
                latex = self._add_refs(latex, "JPEG")


            # --- 7. QUANTIZATION ---
            if 'quantization_analysis' in f_analyses and self.config.get('report_quantization', True):
                qa = f_analyses['quantization_analysis']
                q_info = qa.get('q_matrix_info', {})
                conc = qa.get('conclusion', '')
                
                latex += r"\subsection{Análise de Quantização (Q-Matrices)}"
                
                # Educational foundation
                latex += r"\begin{tcolorbox}[colback=lightgray,title=O que é a Análise de Quantização?]"
                latex += r"\textbf{Conceito:} A quantização é o processo de reduzir a precisão dos dados de vídeo para permitir a compressão. "
                latex += r"Ela utiliza matrizes de ponderação (Scaling Lists) para determinar quais detalhes visuais devem ser priorizados ou descartados."
                latex += r"\vspace{0.2cm}"
                latex += r"\textbf{Significado Forense:} Cada fabricante de câmera e cada software de edição utiliza 'receitas' de quantização específicas. "
                latex += r"A presença de matrizes customizadas ou perfis de compressão avançados (High Profile) ajuda a identificar a \textbf{assinatura do encoder} "
                latex += r"e o nível de preservação da integridade original dos dados."
                latex += r"\end{tcolorbox}"

                # Metodologia e Discussão
                latex += r"\begin{tcolorbox}[colback=white,colframe=secondary,title=Metodologia e Valores de Referência]"
                latex += r"\textbf{1. Matrizes de Escalonamento (Scaling Lists):}"
                latex += r"\begin{itemize}[leftmargin=1cm]"
                latex += r"\item \textbf{Uniforme (Padrão/Flat):} Matrizes uniformes. Típico de encoders básicos ou compressão focada em velocidade."
                latex += r"\item \textbf{Personalizada (Custom):} Matrizes otimizadas para visão humana. Comum em câmeras de alta qualidade ou softwares profissionais (ex: x264 High Profile)."
                latex += r"\end{itemize}"
                latex += r"\vspace{0.2cm}"
                latex += r"\textbf{2. Densidade de Dados (Bits per Pixel - BPP):}"
                latex += r"Mede a quantidade de informação armazenada para cada pixel de cada quadro."
                latex += r"\begin{itemize}[leftmargin=1cm]"
                latex += r"\item \textbf{< 0.10:} Compressão agressiva. Perda provável de evidências microscópicas (ruído de sensor)."
                latex += r"\item \textbf{0.10 - 0.25:} Equilíbrio padrão de mercado (streaming/web)."
                latex += r"\item \textbf{> 0.25:} Alta fidelidade. Preservação excelente para análise forense."
                latex += r"\end{itemize}"
                latex += r"\end{tcolorbox}"

                if conc:
                    latex += r"\subsubsection*{Diagnóstico da Assinatura}"
                    latex += r"\begin{tcolorbox}[colback=success!5,colframe=primary,title=Conclusão de Quantização]"
                    latex += esc(conc)
                    latex += r"\end{tcolorbox}"
                
                latex += r"\begin{longtable}{p{6cm} p{8cm}}"
                latex += r"\toprule \textbf{Parâmetro} & \textbf{Valor} \\ \midrule "
                
                # Tradução de termos técnicos
                trans = {
                    "Unknown": "Desconhecido",
                    "N/A": "N/D",
                    "High": "High (Alta Performance)",
                    "Main": "Main (Padrão)",
                    "Baseline": "Baseline (Simples)",
                    "CABAC": "CABAC (Eficiente)",
                    "CAVLC": "CAVLC (Simples)"
                }
                
                sps = "Detectado" if q_info.get('sps_found') else "Não Detectado"
                custom = "Personalizada (Custom)" if q_info.get('has_custom_scaling_matrix') else "Uniforme (Padrão)"
                prof_raw = str(q_info.get('profile_idc', 'Unknown'))
                prof = esc(trans.get(prof_raw, prof_raw))
                
                refs = str(q_info.get('num_ref_frames', '0'))
                entropy_raw = str(q_info.get('entropy_coding', 'N/A'))
                entropy = esc(trans.get(entropy_raw, entropy_raw))
                scan = esc(str(q_info.get('scan_type', 'N/D')).replace("Unknown", "Desconhecido"))
                
                bpp_info = qa.get('bpp_info', {})
                bpp = bpp_info.get('bpp', 0)
                bpp_str = f"{bpp:.3f}" if bpp > 0 else "N/D"
                
                latex += f"Assinatura de Sequência (SPS) & {sps} \\\\ \\hline \n"
                latex += f"Perfil de Compressão (Profile) & {prof} \\\\ \\hline \n"
                latex += f"Matrizes de Ponderação & {custom} \\\\ \\hline \n"
                latex += f"Quadros de Referência (Refs) & {refs} \\\\ \\hline \n"
                latex += f"Codificação de Entropia & {entropy} \\\\ \\hline \n"
                latex += f"Varredura (Scan Type) & {scan} \\\\ \\hline \n"
                latex += f"Densidade de Bits (BPP) & {bpp_str} \\\\ \\hline \n"
                latex += r"\bottomrule \end{longtable}"
                
                latex = self._add_refs(latex, "QUANTIZATION")

            # --- 8. PRNU INDIVIDUAL ---
            if 'prnu_analysis' in f_analyses and self.config.get('report_prnu', True):
                prnu = f_analyses['prnu_analysis']
                status = prnu.get('status', 'N/A')
                res = prnu.get('resolution', 'N/A')
                
                latex += r"\subsection{Análise PRNU (Identificação de Fonte)}"
                if status == 'extracted':
                    latex += r"\begin{tcolorbox}[colback=success!10,title=Status]"
                    latex += f"Fingerprint extraído com sucesso. Resolução: {res}"
                    latex += r"\end{tcolorbox}"
                else:
                    latex += f"Falha na extração: {prnu.get('error','Unknown')}"
                    latex += r"\end{tcolorbox}"
                
                latex = self._add_refs(latex, "PRNU")
            
            # --- AUDIO ANALYSIS SECTION ---
            audio_data = f_analyses.get('audio_analysis')
            
            if audio_data and self.config.get('report_audio_metadata', True):
                latex += r"\subsection{Análise Forense de Áudio}"
                
                if audio_data.get('status') == 'error':
                     latex += r"\begin{tcolorbox}[colback=danger!10,title=Erro na Análise]"
                     latex += r"Falha ao executar análise de áudio: " + esc(audio_data.get('error', 'Erro desconhecido'))
                     latex += r"\end{tcolorbox}"
                
                analyses = audio_data.get('analyses', {})
                
                # Hash display for Audio
                file_hash = audio_data.get('file_hash', 'N/A')
                stream_hash = audio_data.get('stream_hash', 'N/A')
                
                latex += r"\subsubsection*{Identificação Digital (Hash)}"
                latex += r"\begin{tcolorbox}[colback=white,colframe=gray]"
                latex += r"\textbf{File Hash (Container):} \blackurl{" + str(file_hash) + r"} \\\\"
                if stream_hash and stream_hash != file_hash:
                    latex += r"\textbf{Audio Stream Hash:} \blackurl{" + str(stream_hash) + r"}"
                else:
                    latex += r"\textit{Nota: O hash do fluxo coincide com o do container ou não foi possível calcular separadamente.}"
                latex += r"\end{tcolorbox}"

                # METADATA
                meta = analyses.get('metadata', {})
                if meta and 'error' not in meta:
                    latex += r"\subsubsection{Metadados do Áudio}"
                    latex += r"\begin{longtable}{p{5cm} p{10cm}}"
                    latex += r"\toprule \textbf{Propriedade} & \textbf{Valor} \\ \midrule "
                    latex += r"\endhead "
                    
                    latex += f"Formato & {esc(str(meta.get('format_long', meta.get('format', 'N/A'))))} \\\\ \\hline \n"
                    latex += f"Codec & {esc(str(meta.get('codec_long', meta.get('codec', 'N/A'))))} \\\\ \\hline \n"
                    latex += f"Duração & {meta.get('duration_seconds', 0):.2f}s \\\\ \\hline \n"
                    latex += f"Bitrate & {meta.get('bitrate_kbps', 0)} kbps \\\\ \\hline \n"
                    latex += f"Sample Rate & {meta.get('sample_rate', 0)} Hz \\\\ \\hline \n"
                    latex += f"Canais & {meta.get('channels', 0)} ({esc(str(meta.get('channel_layout', '')))}) \\\\ \\hline \n"
                    
                    latex += r"\bottomrule \end{longtable}"
                    
                    # Encoder hints
                    hints = meta.get('encoder_hints', [])
                    if hints:
                        latex += r"\subsubsection*{Assinaturas de Software Detectadas}"
                        latex += r"\begin{tcolorbox}[colback=warning!10,colframe=warning]"
                        for h in hints:
                            latex += esc(h) + r" \\\\ "
                        latex += r"\end{tcolorbox}"
                    
                    # Forensic note
                    note = meta.get('forensic_note', '')
                    if note:
                        latex += r"\begin{tcolorbox}[colback=lightgray,title=Nota Forense]"
                        latex += esc(note)
                        latex += r"\end{tcolorbox}"
                
                # SPECTRAL STATS
                spectral = analyses.get('spectral', {})
                if spectral and self.config.get('report_audio_spectral', True):
                    latex += r"\subsubsection{Estatísticas Espectrais}"
                    
                    # Metodologia Explicativa
                    latex += r"\begin{tcolorbox}[colback=lightgray,title=Metodologia: Análise Espectral]"
                    latex += r"Esta análise examina a distribuição estatística da energia nas frequências do áudio para identificar inconsistências decorrentes de manipulação:"
                    latex += r"\begin{itemize}[leftmargin=1cm]"
                    latex += r"\item \textbf{Centroide Espectral:} Ponto de equilíbrio do espectro. Mudanças abruptas não naturais indicam possíveis pontos de corte."
                    latex += r"\item \textbf{Largura de Banda:} Faixa de frequências ocupada. O corte abrupto em altas frequências (ex: $>$16kHz) revela compressão com perdas (MP3/AAC)."
                    latex += r"\item \textbf{Quedas de Energia:} Silêncios absolutos ou interrupções súbitas no fluxo espectral sugerem deleção de trechos ou perda de pacotes."
                    latex += r"\end{itemize}"
                    latex += r"\end{tcolorbox}"
                    
                    latex += r"\begin{longtable}{p{6cm} p{9cm}}"
                    latex += r"\toprule \textbf{Métrica} & \textbf{Valor} \\ \midrule "
                    latex += r"\endhead "
                    
                    cent = spectral.get('centroid_hz', {})
                    latex += f"Centroide Espectral & {cent.get('mean', 0):.1f} Hz ($\\sigma$={cent.get('std', 0):.1f}) \\\\ \\hline \n"
                    
                    bw = spectral.get('bandwidth_hz', {})
                    latex += f"Largura de Banda & {bw.get('mean', 0):.1f} Hz ($\\sigma$={bw.get('std', 0):.1f}) \\\\ \\hline \n"
                    
                    latex += f"Frequência Máxima Útil & {spectral.get('max_useful_frequency_hz', 0)/1000:.1f} kHz \\\\ \\hline \n"
                    
                    drops = spectral.get('significant_energy_drops', 0)
                    drop_color = "danger" if drops > 5 else "black"
                    latex += f"Quedas Abruptas de Energia & \\textcolor{{{drop_color}}}{{{drops}}} \\\\ \\hline \n"
                    
                    latex += r"\bottomrule \end{longtable}"
                    
                    note = spectral.get('forensic_note', '')
                    if note and note != 'Características espectrais dentro do esperado':
                        latex += r"\begin{tcolorbox}[colback=warning!10,title=Anomalia Espectral Detectada]"
                        latex += r"\textbf{Interpretação Forense:} O sistema detectou desvios estatísticos significativos que sugerem a presença de edições ou recompressão no arquivo. "
                        latex += esc(note)
                        latex += r"\end{tcolorbox}"
                    
                    latex = self._add_refs(latex, "AUDIO")
                
                # PHASE DISCONTINUITIES
                phase = analyses.get('phase', {})
                if phase and self.config.get('report_audio_phase', True):
                    latex += r"\subsubsection{Detecção de Descontinuidade de Fase}"
                    
                    latex += r"\begin{tcolorbox}[colback=lightgray,title=Metodologia: Análise de Fase]"
                    latex += r"A fase representa o alinhamento temporal das ondas sonoras. Em uma gravação contínua, a fase evolui suavemente:"
                    latex += r"\begin{itemize}[leftmargin=1cm]"
                    latex += r"\item \textbf{Continuidade de Fase:} Cortes e colagens (splicing) criam saltos instantâneos na fase que são matematicamente detectáveis."
                    latex += r"\item \textbf{Consistência de Rede:} Se presente, o zumbido elétrico serve como marca d'água. Saltos na fase dessa frequência indicam edição."
                    latex += r"\end{itemize}"
                    latex += r"\end{tcolorbox}"
                    
                    hc = phase.get('high_confidence_count', 0)
                    color = "danger" if hc > 2 else ("warning" if hc > 0 else "success")
                    
                    latex += r"\begin{tcolorbox}[colback=" + color + r"!10,colframe=" + color + r"]"
                    latex += f"\\textbf{{Descontinuidades de alta confiança detectadas: {hc}}}"
                    latex += r"\end{tcolorbox}"
                    
                    note = phase.get('forensic_note', '')
                    if note:
                        latex += r"\noindent " + esc(note)
                        latex += r"\vspace{0.3cm}"
                    
                    discs = phase.get('discontinuities', [])
                    if discs:
                        latex += r"\begin{longtable}{p{4cm} p{4cm}}"
                        latex += r"\toprule \textbf{Tempo (s)} & \textbf{Confiança} \\ \midrule "
                        latex += r"\endhead "
                        for d in discs[:10]:
                            latex += f"{d.get('time_seconds', 0):.3f} & {d.get('confidence', 0)*100:.0f}\\% \\\\ \\hline \n"
                        latex += r"\bottomrule \end{longtable}"
                    
                    latex = self._add_refs(latex, "AUDIO")
                
                # SILENCE ANALYSIS
                silence = analyses.get('silence', {})
                if silence and self.config.get('report_audio_silence', True):
                    latex += r"\subsubsection{Detecção de Silêncio Anômalo}"
                    
                    latex += r"\begin{tcolorbox}[colback=lightgray,title=Metodologia: Análise de Ruído e Silêncio]"
                    latex += r"Analisa a continuidade do ruído de fundo (noise floor). Em gravações de microfone autênticas, o silêncio nunca é absoluto (zero digital) devido ao ruído térmico e ambiental:"
                    latex += r"\begin{itemize}[leftmargin=1cm]"
                    latex += r"\item \textbf{Silêncio Digital:} Trechos de amplitude zero (-inf dB) são matematicamente impossíveis em capturas naturais. Indicam deleção (trimming) ou inserção de silêncio sintético."
                    latex += r"\item \textbf{Descontinuidades de Ruído:} Mudanças abruptas no 'noise floor' sugerem a junção de grampos distintos."
                    latex += r"\end{itemize}"
                    latex += r"\end{tcolorbox}"
                    
                    # Contexto sobre DTX e Comfort Noise
                    latex += r"\begin{tcolorbox}[colback=white,colframe=secondary,title=Considerações sobre Telefonia Celular e Gravações de Apps]"
                    latex += r"\textbf{Telefonia Celular (AMR, EVS, etc.):} Codecs de telefonia utilizam \textit{DTX} (Discontinuous Transmission) para economizar banda. "
                    latex += r"Durante pausas de silêncio (ex: respiração), o codec transmite frames especiais. Na decodificação, esses silêncios são substituídos por "
                    latex += r"\textit{Comfort Noise} (ruído sintético gerado por modelo estatístico), \textbf{não por zeros}. Portanto, zeros perfeitos no meio de áudio de telefonia são altamente anômalos."
                    latex += r"\\[0.2cm]"
                    latex += r"\textbf{Gravações de Apps Nativos:} Aplicativos de gravação em celular frequentemente inserem zeros no \textbf{início (lead-in)} e \textbf{fim (lead-out)} da gravação. "
                    latex += r"A duração desses zeros pode variar conforme o SO (Android/iOS), versão e modelo do dispositivo. Esses zeros são comportamento normal e esperado."
                    latex += r"\end{tcolorbox}"
                    
                    # Estatísticas com classificação por posição
                    digital_middle = silence.get('digital_middle_count', 0)
                    digital_edge = silence.get('digital_edge_count', 0)
                    digital_total = silence.get('digital_silence_count', 0)
                    
                    # Alerta para zeros no meio (altamente suspeito)
                    if digital_middle > 0:
                        latex += r"\begin{tcolorbox}[colback=danger!10,colframe=danger,title=ALERTA: Silêncio Digital no Meio do Áudio]"
                        latex += f"\\textbf{{{digital_middle}}} segmento(s) de silêncio digital perfeito detectado(s) no \\textbf{{MEIO}} do áudio. "
                        latex += r"Isso é altamente suspeito de inserção artificial ou manipulação. "
                        latex += r"Em telefonia celular, silêncios são preenchidos por Comfort Noise (DTX), não por zeros perfeitos. "
                        latex += r"Em gravações diretas, silêncios reais geram ruído térmico, não zeros matemáticos."
                        latex += r"\end{tcolorbox}"
                    
                    # Informação sobre zeros nas bordas (menos suspeito)
                    if digital_edge > 0:
                        latex += r"\begin{tcolorbox}[colback=warning!10,colframe=warning,title=Silêncio Digital no Início/Fim]"
                        latex += f"\\textbf{{{digital_edge}}} segmento(s) de silêncio digital detectado(s) no início ou fim do áudio. "
                        latex += r"Este comportamento é \textbf{comum} em gravações de apps nativos de celular (lead-in/lead-out). "
                        latex += r"A duração desses zeros pode variar conforme SO, versão e modelo do dispositivo."
                        latex += r"\end{tcolorbox}"
                    
                    # Sem silêncio digital
                    if digital_total == 0:
                        latex += r"\begin{tcolorbox}[colback=success!10,colframe=success]"
                        latex += r"Nenhum silêncio digital artificial detectado."
                        latex += r"\end{tcolorbox}"
                    
                    latex += f"\\noindent Total de pausas: {silence.get('silence_count', 0)} ({silence.get('silence_percentage', 0):.1f}\\% do áudio)"
                    latex += r"\vspace{0.3cm}"
                    
                    note = silence.get('forensic_note', '')
                    if note and note != 'Padrões de silêncio dentro do esperado':
                        latex += r"\noindent\textit{" + esc(note) + r"}"
                        latex += r"\vspace{0.3cm}"
                    
                    # Tabela de segmentos de silêncio digital
                    segments = silence.get('segments', [])
                    digital_segments = [s for s in segments if s.get('is_digital_silence', False)]
                    
                    if digital_segments:
                        latex += r"\subsubsection*{Segmentos de Silêncio Digital Detectados}"
                        latex += r"\begin{longtable}{c c c c c}"
                        latex += r"\toprule \textbf{Início (s)} & \textbf{Fim (s)} & \textbf{Duração (s)} & \textbf{Posição} & \textbf{Anomalia} \\ \midrule "
                        latex += r"\endhead "
                        
                        for seg in digital_segments[:15]:  # Limitar a 15 segmentos
                            start = seg.get('start_seconds', 0)
                            end = seg.get('end_seconds', 0)
                            dur = seg.get('duration_seconds', 0)
                            pos = seg.get('position', 'unknown')
                            score = seg.get('anomaly_score', 0)
                            
                            # Traduzir posição
                            pos_text = {"start": "Início", "end": "Fim", "middle": "Meio"}.get(pos, pos)
                            
                            # Cor baseada no score
                            score_color = "danger" if score > 0.5 else ("warning" if score > 0.2 else "success")
                            
                            latex += f"{start:.3f} & {end:.3f} & {dur:.3f} & {pos_text} & \\textcolor{{{score_color}}}{{{score*100:.0f}\\%}} \\\\ \\hline \n"
                        
                        if len(digital_segments) > 15:
                            latex += f"\\multicolumn{{5}}{{c}}{{\\textit{{... e mais {len(digital_segments) - 15} segmento(s)}}}} \\\\ \\hline\n"
                        
                        latex += r"\bottomrule \end{longtable}"
                        latex += r"\vspace{0.3cm}"
                    
                    latex = self._add_refs(latex, "AUDIO")
            
            # --- AUDIO DEEPFAKE SECTION ---
            audio_df = f_analyses.get('audio_deepfake')
            if audio_df and audio_df.get('status') != 'error' and self.config.get('report_audio_deepfake', True):
                latex += r"\subsection{Detecção de Áudio Sintético (Deepfake de Voz)}"
                
                latex += r"\begin{tcolorbox}[colback=lightgray,title=Metodologia]"
                latex += r"Esta análise aplica técnicas heurísticas para detectar características de síntese de voz (TTS, voice cloning):"
                latex += r"\begin{itemize}[leftmargin=1cm]"
                latex += r"\item \textbf{Padrões de Mel-Spectrogram:} Detecta uniformidade excessiva e periodicidade artificial."
                latex += r"\item \textbf{Consistência de Formantes:} Verifica se formantes vocais variam naturalmente."
                latex += r"\item \textbf{Estabilidade de Pitch:} Tom de voz excessivamente estável indica síntese."
                latex += r"\item \textbf{Padrões de Pausas:} Micro-pausas de respiração ausentes sugerem TTS."
                latex += r"\end{itemize}"
                latex += r"\end{tcolorbox}"
                
                # Veredicto
                score = audio_df.get('overall_score', 0)
                verdict = audio_df.get('verdict', 'unknown')
                verdict_text = audio_df.get('verdict_text', '')
                
                if verdict == 'highly_suspicious':
                    color = "danger"
                elif verdict == 'suspicious':
                    color = "warning"
                else:
                    color = "success"
                
                latex += r"\begin{tcolorbox}[colback=" + color + r"!10,colframe=" + color + r",title=Veredicto]"
                latex += f"\\textbf{{Score Geral: {score*100:.0f}\\%}}"
                latex += r"\\[0.2cm]"
                latex += esc(verdict_text)
                latex += r"\end{tcolorbox}"
                
                # Scores table
                analyses_df = audio_df.get('analyses', {})
                latex += r"\begin{longtable}{p{6cm} p{3cm} p{6cm}}"
                latex += r"\toprule \textbf{Análise} & \textbf{Score} & \textbf{Nota} \\ \midrule "
                latex += r"\endhead "
                
                for key, analysis_data in analyses_df.items():
                    if isinstance(analysis_data, dict):
                        sc = analysis_data.get('anomaly_score', 0)
                        note = analysis_data.get('forensic_note', '')
                        sc_color = "danger" if sc > 0.5 else ("warning" if sc > 0.3 else "success")
                        latex += f"{esc(key.replace('_', ' ').title())} & \\textcolor{{{sc_color}}}{{{sc*100:.0f}\\%}} & {esc(note[:60])} \\\\ \\hline \n"
                
                latex += r"\bottomrule \end{longtable}"
                
                latex = self._add_refs(latex, "AUDIO_DEEPFAKE")

            latex += r"\newpage"
        
        # --- 8. PRNU MATRIX (GLOBAL) ---
        prnu_matrix = data.get('prnu_matrix', {})
        if prnu_matrix and 'matrix' in prnu_matrix and self.config.get('report_prnu', True):
            matrix_data = prnu_matrix['matrix']
            files = prnu_matrix.get('files', [])
            
            if len(files) > 1:
                latex += r"\section{Comparação de Fontes (PRNU) - Matriz de Similaridade}"
                
                latex += r"\begin{tcolorbox}[colback=lightgray,title=Metodologia Forense (PRNU)]"
                latex += r"\textbf{Fingerprint de Sensor:} O PRNU (\textit{Photo Response Non-Uniformity}) é um ruído imperceptível e único gerado pelas imperfeições físicas na fabricação do sensor de cada câmera. "
                latex += r"Ele funciona como uma 'impressão digital digital' da câmera."
                latex += r"\vspace{0.2cm}"
                latex += r"\textbf{Correlação PCE:} A comparação utiliza a métrica \textbf{PCE} (\textit{Peak-to-Correlation Energy}). "
                latex += r"Calculamos o quanto o ruído de um arquivo se alinha estatisticamente com o de outro. Valores altos provam cientificamente que as mídias foram gravadas pelo mesmo dispositivo físico."
                latex += r"\end{tcolorbox}"
                
                # Reference Values and Interpretation
                latex += r"\begin{tcolorbox}[colback=white,colframe=secondary,title=Interpretação Forense dos Valores PCE]"
                latex += r"A confiabilidade da identificação de fonte baseia-se nos seguintes limiares técnicos:"
                latex += r"\begin{itemize}[leftmargin=1cm]"
                latex += r"\item \textbf{PCE > 60:} \textbf{MATCH POSITIVO.} Fortíssima evidência de mesma origem. A probabilidade de erro (falso positivo) é estatisticamente desprezível."
                latex += r"\item \textbf{PCE 40 - 60:} \textbf{Indício Forte.} Alta probabilidade de mesma origem, mas recomendável buscar evidências complementares (ex: metadados)."
                latex += r"\item \textbf{PCE < 40:} \textbf{Inconclusivo.} O ruído pode estar muito degradado por compressão agressiva, redimensionamento ou falta de luz, impedindo a correlação segura."
                latex += r"\end{itemize}"
                latex += r"\vspace{0.2cm}"
                latex += r"\textbf{Nota sobre Resize:} Se os arquivos têm resoluções diferentes, o sistema redimensiona os fingerprints para permitir a comparação. Isso pode reduzir o score PCE e é sinalizado com um asterisco (*)."
                latex += r"\end{tcolorbox}"
                
                # Tabela Dinâmica
                # Headers: ID, File, 1, 2, ...
                
                # 1. Legend Table
                latex += r"\subsection*{Legenda dos Arquivos}"
                latex += r"\begin{tabular}{l p{12cm}}"
                latex += r"\toprule \textbf{ID} & \textbf{Arquivo} \\ \midrule "
                for i, fname in enumerate(files):
                     # Use safe url wrapping forced to black
                     fname_clean = r"\blackurl{" + str(fname) + r"}"
                     latex += f"{i+1} & {fname_clean} \\\\ \n"
                latex += r"\bottomrule \end{tabular}"
                
                latex += r"\vspace{0.5cm}"
                
                # 2. Pairwise Comparison List (Tabela Linear para escalabilidade)
                latex += r"\subsection*{Resultados da Comparação (PCE)}"
                
                latex += r"\begin{longtable}{c c c l}"
                latex += r"\toprule \textbf{ID A} & \textbf{ID B} & \textbf{Score PCE} & \textbf{Resultado} \\ \midrule "
                latex += r"\endhead "
                
                # Iterate Upper Triangle Only
                # matrix_data is a list of rows. each row has results.
                # matrix_data[i]['results'][j] is comparison between i and j.
                
                has_comparisons = False
                
                for i in range(len(files)):
                    for j in range(i + 1, len(files)): # Start from i+1 to avoid self and redundant
                        row_data = matrix_data[i]
                        res = row_data['results'][j]
                        
                        pce = res.get('pce', 0)
                        match = res.get('match', False)
                        note = res.get('scaling_note')
                        
                        pce_str = f"{pce:.1f}"
                        if note:
                            pce_str += "*"
                        
                        result_str = r"\textbf{MATCH}" if match else "Inconclusivo"
                        result_color = "success" if match else "black"
                        
                        # Add Row
                        latex += f"{i+1} & {j+1} & {pce_str} & \\textcolor{{{result_color}}}{{{result_str}}} \\\\ \\hline \n"
                        has_comparisons = True
                
                if not has_comparisons:
                     latex += r"\multicolumn{4}{c}{Nenhuma comparação válida realizada.} \\ \hline"

                latex += r"\bottomrule \end{longtable}"
                
                latex += r"\vspace{0.2cm}"
                latex += r"\small \textit{* Asterisco indica redimensionamento de imagem para compatibilizar fingerprints (Resize).}"
                
                latex = self._add_refs(latex, "PRNU")

        # --- FINAL SECTION: ANALYSIS CONFIGURATION ---
        latex += r"\newpage"
        latex += r"\section{Parâmetros de Configuração da Análise}"
        latex += r"Para fins de auditabilidade e reprodutibilidade, seguem os parâmetros técnicos utilizados pelo software durante o processamento deste caso."
        
        latex += r"\begin{table}[h!]\centering"
        latex += r"\renewcommand{\arraystretch}{1.3}" # Mais espaço entre linhas
        latex += r"\begin{tabular}{|p{9cm}|p{6cm}|}"
        latex += r"\hline "
        latex += r"\textbf{Parâmetro / Variável} & \textbf{Valor} \\ \hline "
        
        # Mapeamento estendido com descrições ricas
        friendly_names = {
            # Deepfake
            "deepfake_noise_threshold": "Sensibilidade de Ruído (Splicing)",
            "deepfake_jitter_threshold": "Tolerância a Instabilidade (Jitter)",
            "deepfake_fast_mode": "Modo de Análise Rápido",
            
            # Image Forensics
            "copymove_features": "Máximo de Pontos SIFT (Copy-Move)",
            "copymove_min_cluster": "Mínimo de Clusters (Copy-Move)",
            "resampling_block_size": "Tamanho de Bloco (Resampling)",
            "ela_quality": "Qualidade JPEG de Referência (ELA)",
            
            # Video
            "prnu_frame_limit": "Limite de Quadros para PRNU",
            "scene_threshold": "Sensibilidade de Corte de Cena",
            
            # Audio
            "audio_noise_window": "Janela de Análise de Ruído",
            "audio_silence_threshold": "Limiar de Silêncio Anômalo (dB)",
            "audio_segment_duration": "Duração do Segmento de Amostragem",
            "audio_random_segments": "Qtd. de Segmentos Aleatórios",
            "audio_silence_margin_seconds": "Margem para Zeros no Início/Fim (s)"
        }
        
        # Filtrar apenas chaves de parâmetros (ignorar flags de relatório)
        sorted_keys = sorted(self.config.keys())
        
        for key in sorted_keys:
            if key.startswith("report_"):
                continue
            
            val = self.config[key]
            val_str = "Ativado" if val is True else "Desativado" if val is False else str(val)
            
            desc = friendly_names.get(key, "")
            
            # Formato: Descrição \newline (nome_variavel)
            if desc:
                col1 = f"\\textbf{{{esc(desc)}}} \\newline \\texttt{{\\small ({esc(key)})}}"
            else:
                col1 = f"\\texttt{{{esc(key)}}}"
                
            latex += f"{col1} & {esc(val_str)} \\\\ \\hline \n"
            
        latex += r"\end{tabular}"
        latex += r"\caption{Parâmetros técnicos configurados para esta análise.}"
        latex += r"\end{table}"

        latex += r"\end{document}"
        return latex
