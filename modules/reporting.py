import subprocess
import os
import re
import json
from pathlib import Path
from core.case_manager import CaseManager
from core.utils import get_timestamp_iso
from datetime import datetime

class ReportingModule:
    """Gerador de Relatórios (LaTeX -> PDF)."""
    
    def __init__(self, case_manager: CaseManager):
        self.cm = case_manager
        self.logger = self.cm.get_logger()

    def _format_date(self, iso_str):
        """Formata data ISO para legível com timezone."""
        try:
            dt = datetime.fromisoformat(iso_str)
            return dt.strftime(r"%d/%m/%Y %H:%M (UTC%z)")
        except:
            return iso_str

    def generate(self):
        self.logger.log("REPORT_GEN_START")
        
        # Coletar dados dos resultados
        data = self._collect_data()
        
        # Gerar LaTeX Source
        tex_path = self.cm.report_dir / "report.tex"
        latex_content = self._generate_latex_source(data)
        
        with open(tex_path, 'w', encoding='utf-8') as f:
            f.write(latex_content)
        
        self.logger.log("REPORT_TEX_GENERATED", {"path": str(tex_path)})
            
        # Compilar para PDF
        pdf_path = self.cm.report_dir / "report.pdf"
        try:
            self._compile_latex(tex_path, self.cm.report_dir)
            self.logger.log("REPORT_PDF_GENERATED", {"path": str(pdf_path)})
        except Exception as e:
            self.logger.log("REPORT_COMPILATION_ERROR", {"error": str(e)})
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
                with open(manifest_path, 'r', encoding='utf-8') as f:
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
                            with open(json_path, 'r', encoding='utf-8') as jf:
                                file_entry["analyses"][analysis_type] = json.load(jf)
                                
                    base_data["files"].append(file_entry)
            except Exception as e:
                self.logger.log("MANIFEST_LOAD_ERROR", {"error": str(e)})
                
            # Carregar Matriz PRNU (se existir)
            matrix_path = self.cm.results_dir / "prnu_matrix.json"
            if matrix_path.exists():
                try:
                    with open(matrix_path, 'r', encoding='utf-8') as f:
                        base_data["prnu_matrix"] = json.load(f)
                except Exception as e:
                    self.logger.log("PRNU_MATRIX_LOAD_ERROR", {"error": str(e)})
        else:
            # Modo Legado / Arquivo Único
            single_entry = {"filename": "Arquivo Único", "analyses": {}}
            
            # Mapeamento de nomes de arquivo padrão para chaves de análise
            for res_file in self.cm.results_dir.glob("*.json"):
                if res_file.name == "batch_manifest.json": continue
                
                # Ex: file_analysis.json -> file_analysis
                key = res_file.stem
                try:
                    with open(res_file, 'r', encoding='utf-8') as f:
                        single_entry["analyses"][key] = json.load(f)
                except Exception as e:
                    self.logger.log("DATA_LOAD_ERROR", {"file": res_file.name, "error": str(e)})
            
            if single_entry["analyses"]:
                base_data["files"].append(single_entry)
        
        return base_data

    # Banco de Referências Bibliográficas (ABNT)
    REFERENCES_DB = {
        "ELA": [
            r"KRAWETZ, N. A Picture's Worth: Digital Image Analysis and Forensics. In: \textit{Black Hat Briefings}, Las Vegas, 2007. Disponível em: \url{http://www.hackerfactor.com/}. Acesso em: 2025.",
        ],
        "PRNU": [
            r"CHEN, M. et al. Determining Image Origin and Integrity Using Sensor Noise. \textit{IEEE Transactions on Information Forensics and Security}, v. 3, n. 1, p. 74-90, 2008.",
            r"LUKAS, J.; FRIDRICH, J.; GOLJAN, M. Digital Camera Identification From Sensor Pattern Noise. \textit{IEEE Transactions on Information Forensics and Security}, v. 1, n. 2, p. 205-214, 2006."
        ],
        "COPYMOVE": [
            r"AMERINI, I. et al. A SIFT-Based Forensic Method for Copy-Move Attack Detection and Transformation Recovery. \textit{IEEE Transactions on Information Forensics and Security}, v. 6, n. 3, p. 1099-1110, 2011.",
            r"CHRISTLEIN, V. et al. An Evaluation of Popular Copy-Move Forgery Detection Approaches. \textit{IEEE Transactions on Information Forensics and Security}, v. 7, n. 6, p. 1841-1854, 2012."
        ],
        "RESAMPLING": [
            r"POPESCU, A. C.; FARID, H. Exposing Digital Forgeries by Detecting Traces of Re-sampling. \textit{IEEE Transactions on Signal Processing}, v. 53, n. 2, p. 758-767, 2005.",
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
            r"SWAMINATHAN, A. et al. Digital Image Forensics. \textit{IEEE Signal Processing Magazine}, v. 26, n. 2, p. 89-98, 2009.",
            r"LIN, Z. et al. Fast, Automatic and Fine-Grained Tampered JPEG Image Detection via DCT Coefficient Analysis. \textit{Pattern Recognition}, v. 42, n. 11, p. 2492-2501, 2009."
        ],
         "COMPRESSION": [
            r"WANG, W.; FARID, H. Exposing Digital Forgeries in Video by Detecting Double MPEG Compression. In: \textit{Proceedings of the 8th Workshop on Multimedia and Security}. ACM, 2006. p. 37-47."
        ],
        "DEEPFAKE": [
            r"DURALL, R. et al. Watch your Up-Convolution: CNN Based Generative Models Yield Artificial Frequency Patterns. \textit{Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition}, 2020.",
            r"OJALA, T. et al. Multiresolution Gray-Scale and Rotation Invariant Texture Classification with Local Binary Patterns. \textit{IEEE Transactions on Pattern Analysis and Machine Intelligence}, v. 24, n. 7, p. 971-987, 2002."
        ]
    }

    def _add_refs(self, latex, key):
        """Adiciona bloco de referências bibliográficas se existirem."""
        refs = self.REFERENCES_DB.get(key)
        if not refs: return latex
        
        latex += r"\vspace{0.3cm}"
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
        
        for i in range(3):
            # cwd=str(output_dir) é crucial
            res = subprocess.run(cmd, cwd=str(output_dir), capture_output=True, text=True)
            if res.returncode != 0:
                if i == 0: continue 
                raise RuntimeError(f"pdflatex failed (Pass {i+1}): {res.stderr or res.stdout}")

    def _generate_latex_source(self, data):
        """Gera o código fonte LaTeX completo."""
        esc = self._escape_latex
        
        latex = r"""
\documentclass[a4paper,12pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage[brazil]{babel}
\usepackage{geometry}
\usepackage{xcolor}
\usepackage{booktabs}
\usepackage{longtable}
\usepackage{enumitem}
\usepackage{graphicx}
\usepackage{hyperref}
\usepackage{float}
\usepackage{colortbl}
\usepackage{tcolorbox}
\usepackage{fancyhdr}
\usepackage{seqsplit}

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
\rhead{\small \textcolor{gray}{\today}}
\cfoot{\thepage}

\title{\textbf{\textcolor{primary}{Relatório de Análise Forense de Imagem/Vídeo}}}
\date{\today}

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
            f_name = esc(file_entry.get('filename', 'Desconhecido'))
            f_analyses = file_entry.get('analyses', {})
            
            latex += f"\\section{{Arquivo: {f_name}}}\n"
            
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
            if 'file_analysis' in f_analyses:
                fa = f_analyses['file_analysis']
                meta = fa.get('metadata', {})
                fmt = meta.get('format', {})
                
                latex += r"\subsection{Metadados do Arquivo}"
                
                # Hash
                latex += r"\subsubsection*{Identificação Digital (Hash)}"
                latex += r"\begin{tcolorbox}[colback=white,colframe=gray]"
                latex += r"\textbf{SHA-512:} \texttt{\seqsplit{" + esc(fa.get('file_hash', 'N/A')) + r"}}"
                latex += r"\end{tcolorbox}"
                
                # Format Table
                latex += r"\subsubsection*{Formato e Container}"
                latex += r"\begin{longtable}{p{5cm} p{10cm}}"
                latex += r"\toprule \textbf{Propriedade} & \textbf{Valor} \\ \midrule "
                latex += r"\endhead "
                
                for k, v in fmt.items():
                    if not isinstance(v, (dict, list)):
                        latex += f"\\textbf{{{esc(k)}}} & {esc(str(v))} \\\\ \\hline \n"
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
                    
                    conclusion = esc(proc.get('conclusion', ''))
                    is_detected = proc.get('detected', False)
                    color = "danger" if is_detected else "success"
                    
                    latex += r"\begin{tcolorbox}[colback=white,colframe=" + color + r",title=Avaliação Automática]"
                    latex += r"\textbf{" + conclusion + r"}"
                    latex += r"\end{tcolorbox}"
                    
                    traces = proc.get('traces_found', [])
                    if traces:
                        latex += r"\subsubsection*{Assinaturas de Software Encontradas}"
                        latex += r"\begin{longtable}{p{4cm} p{4cm} p{7cm}}"
                        latex += r"\toprule \textbf{Origem} & \textbf{Chave} & \textbf{Valor} \\ \midrule "
                        latex += r"\endhead "
                        for t in traces:
                            latex += f"{esc(t.get('source','-'))} & {esc(t.get('key','-'))} & {esc(str(t.get('value','-'))[:50])} \\\\ \\hline \n"
                        latex += r"\bottomrule \end{longtable}"

                # --- 4. GOP ---
                gop = fa.get('gop_stats', {})
                latex += r"\subsection{Estrutura de Compressão (GOP)}"
                
                # Help Box
                latex += r"\begin{tcolorbox}[colback=lightgray,title=O que é GOP?]"
                latex += r"O \textit{Group of Pictures} define a compressão temporal. Alterações na estrutura (ex: GOP fixo vs variável) podem indicar manipulação."
                latex += r"\end{tcolorbox}"
                
                latex += r"\begin{itemize}"
                latex += f"\\item \\textbf{{Total de Frames:}} {gop.get('total_frames_analyzed', 0)}"
                latex += f"\\item \\textbf{{I-Frames (Keyframes):}} {gop.get('i_frames', 0)}"
                latex += f"\\item \\textbf{{P-Frames:}} {gop.get('p_frames', 0)}"
                latex += f"\\item \\textbf{{B-Frames:}} {gop.get('b_frames', 0)}"
                latex += f"\\item \\textbf{{Tamanho Médio do GOP:}} {gop.get('avg_gop_size', 0):.2f}"
                latex += r"\end{itemize}"

            # --- 5. CONTINUITY ---
            if 'continuity_analysis' in f_analyses:
                ca = f_analyses['continuity_analysis']
                cuts = ca.get('cuts_detected', [])
                total = ca.get('total_cuts', 0)
                
                latex += r"\subsection{Análise de Continuidade Visual}"
                
                latex += r"\begin{tcolorbox}[colback=lightgray,title=Entendendo esta Análise]"
                latex += r"Detecta cortes bruscos ('cortes secos'). Em gravações contínuas, cortes indicam edição/supressão."
                latex += r"\end{tcolorbox}"
                
                latex += f"\\textbf{{Resumo:}} Foram detectadas {total} descontinuidades visuais."
                
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
                        except:
                            ts_str = str(ts)
                        
                        msg = esc(anomaly.get('message', ''))
                        latex += f"{ts_str} & {msg} \\\\ \\hline \n"
                        
                    latex += r"\bottomrule \end{longtable}"


            # --- STRUCTURE ANALYSIS ---
            if 'structure_analysis' in f_analyses:
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
                if "Fast-Start" in conc: color = "warning!5"
                elif "Capture" in conc: color = "success!5"
                
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
                    
                    desc = ""
                    if atype == 'ftyp': desc = r" \textit{(Header)}"
                    elif atype == 'moov': desc = r" \textit{(Index/Metadados)}"
                    elif atype == 'mdat': desc = r" \textit{(Stream de Mídia)}"
                    elif atype == 'free': desc = r" \textit{(Padding)}"
                    
                    # Highlight critical atoms
                    if atype in ['moov', 'mdat']:
                        latex += f"\\item \\textbf{{\\texttt{[{atype}]}}} (Offset: {offset}, Size: {size} bytes){desc}"
                    else:
                        latex += f"\\item \\texttt{[{atype}]} (Offset: {offset}){desc}"
                latex += r"\end{itemize}"

            # --- 6. STATISTICAL COMPRESSION ---
            if 'compression_analysis' in f_analyses:
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
                
                # Explicação Metodológica
                latex += r"\begin{tcolorbox}[colback=white,colframe=secondary,title=Interpretação Forense por Tipo de Quadro]"
                latex += r"\begin{itemize}"
                latex += r"\item \textbf{Quadros I (Intra):} Anomalias sugerem \textbf{edição espacial} (crop, resize, overlay)."
                latex += r"\item \textbf{Quadros P/B (Preditivos):} Desvios indicam \textbf{manipulação temporal} ou \textbf{recompressão} (estrutura de GOP alterada)."
                latex += r"\item \textbf{Global:} Visão geral da integridade estatística do fluxo de dados."
                latex += r"\end{itemize}"
                latex += r"\end{tcolorbox}"
                
                # Detectar formato (Segmentado vs Legado)
                if 'global' in benford:
                    segments = ['global', 'I', 'P', 'B']
                else:
                    segments = ['global']
                    benford = {'global': benford}
                
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
                        st = esc(b_data.get('status', 'N/A'))
                        
                        if sc > 0.15: row_col = r"\rowcolor{danger!15}"
                        elif sc > 0.10: row_col = r"\rowcolor{warning!15}"
                        else: row_col = ""
                        
                    seg_name = seg.upper() if seg != 'global' else "GLOBAL"
                    latex += f"{row_col} \\textbf{{{seg_name}}} & {score_fmt} & {st} \\\\ \\hline \n"
                    
                latex += r"\bottomrule \end{longtable}"
                
                # Tabela Detalhada (Global)
                b_global = benford.get('global', {})
                obs = b_global.get('observed_freq', [])
                exp = b_global.get('expected_freq', [])
                
                if obs and len(obs) == 9:
                    latex += r"\subsubsection*{Detalhamento por Dígito (Global)}"
                    latex += r"\textit{\small Desvios > 5\% destacados em laranja.}"
                    latex += r"\begin{tabular}{r r r r}"
                    latex += r"\toprule \textbf{Díc.} & \textbf{Obs.} & \textbf{Esp.} & \textbf{Desvio} \\ \midrule "
                    for i in range(9):
                        o = obs[i]
                        e = exp[i]
                        d = o - e
                        row_color = r"\rowcolor{danger!20}" if abs(d) > 0.05 else ""
                        latex += f"{row_color} {i+1} & {o*100:.1f}\\% & {e*100:.1f}\\% & {d*100:+.1f}\\% \\\\ \n"
                    latex += r"\bottomrule \end{tabular}"

                # FOURIER
                f_status = esc(fourier.get('status', 'N/A'))
                f_period = fourier.get('dominant_period_frames', 0)
                f_strength = fourier.get('peak_strength', 0)
                
                latex += r"\subsubsection{Análise de Periodicidade (Estrutura GOP)}"
                
                latex += r"\begin{tcolorbox}[colback=white,colframe=secondary,title=Interpretação]"
                latex += r"Verifica se o vídeo possui uma 'pulsação' rítmica na compressão. GOPs fixos e rígidos (comum em edição) geram pulsação forte."
                latex += r"\end{tcolorbox}"
                
                latex += r"\begin{longtable}{p{6cm} p{8cm}}"
                latex += r"\toprule \textbf{Métrica} & \textbf{Resultado} \\ \midrule "
                latex += f"Periodicidade (GOP) & {f_period:.1f} frames \\\\ \\hline \n"
                latex += f"Força do Padrão & {f_strength:.2f} (Limiar > 3.0 é forte) \\\\ \\hline \n"
                latex += f"Diagnóstico & {f_status} \\\\ \\hline \n"
                latex += r"\bottomrule \end{longtable}"
                
                if conclusion:
                    bg_conc = "danger!10" if "viola" in conclusion or "rígida" in conclusion else "success!10"
                    latex += r"\subsection*{Conclusão Estatística}"
                    latex += r"\begin{tcolorbox}[colback=" + bg_conc + r"]"
                    latex += conclusion
                    latex += r"\end{tcolorbox}"

            # --- 7. IMAGE ANALYSIS (ELA) ---
            if 'image_analysis' in f_analyses:
                img_an = f_analyses['image_analysis']
                meta = img_an.get('metadata', {})
                ela = img_an.get('ela_analysis', {})
                img_hash = img_an.get('file_hash', 'N/A')
                prnu_img = img_an.get('prnu_analysis', {})
                
                latex += r"\subsection{Metadados da Imagem}"
                latex += r"\begin{tcolorbox}[colback=white,colframe=gray]"
                latex += r"\textbf{SHA-512:} \texttt{\seqsplit{" + esc(img_hash) + r"}}"
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
                except:
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

                # ELA Section
                latex += r"\subsection{Análise de Nível de Erro (ELA)}"
                
                latex += r"\begin{tcolorbox}[colback=lightgray,title=Metodologia ELA]"
                latex += r"A Error Level Analysis identifica áreas da imagem com diferentes níveis de compressão JPEG. Em uma imagem original, o erro deve ser uniforme. Áreas mais brilhantes ou com padrões diferentes podem indicar manipulação digital (colagens, pincéis)."
                latex += r"\end{tcolorbox}"
                
                if ela.get('status') == 'success':
                    ela_score = ela.get('ela_score', 0)
                    ela_img_file = ela.get('ela_image')
                    amp = ela.get('amplification_factor', 15)
                    
                    latex += f"\\textbf{{Score de Diferença Global:}} {ela_score:.2f} (Amplificação: {amp}x)\n\n"
                    latex += r"\vspace{0.5cm}"
                    
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

            if noise_data:
                noise = noise_data
                stats = noise.get('global_stats', {})
                outliers = noise.get('outliers_detected', 0)
                map_file = noise.get('map_image')
                
                latex += r"\subsection{Análise de Consistência de Ruído}"
                
                latex += r"\begin{tcolorbox}[colback=lightgray,title=Metodologia]"
                latex += r"A imagem é dividida em blocos de 64x64 pixels. Para cada bloco, calculamos a variância e entropia do ruído residual. Desvios significativos (Outliers > 3$\sigma$) indicam regiões que não pertencem à distribuição original (ex: colagens)."
                latex += r"\end{tcolorbox}"
                
                if noise.get('status') == 'success':
                    # Global Statistics
                    latex += r"\noindent\textbf{Estatísticas Globais de Ruído:}"
                    latex += r"\begin{itemize}"
                    latex += f"\\item \\textbf{{Variância Média:}} {stats.get('mean_variance',0):.2f}"
                    latex += f"\\item \\textbf{{Desvio Padrão (das Variâncias):}} {stats.get('std_variance',0):.2f}"
                    latex += f"\\item \\textbf{{Entropia Média:}} {stats.get('mean_entropy',0):.3f}"
                    latex += f"\\item \\textbf{{Blocos Anômalos (Outliers):}} {outliers} detectados."
                    latex += r"\end{itemize}"
                    
                    # Heatmap
                    if map_file:
                        rel_path = f"../results/{map_file}"
                        latex += r"\begin{figure}[H]"
                        latex += r"\centering"
                        latex += f"\\includegraphics[width=0.85\\textwidth]{{{rel_path}}}"
                        latex += r"\caption{Mapa de Distribuição de Ruído (JET Colormap)}"
                        latex += r"\end{figure}"
                        
                    # Conclusion
                    if outliers > 0:
                        latex += r"\begin{tcolorbox}[colback=warning!10,title=Alerta de Inconsistência]"
                        latex += r"Foram detectadas regiões com padrões de ruído estatisticamente divergentes do restante da imagem. Verifique as áreas vermelhas/azuis intensas no mapa acima."
                        latex += r"\end{tcolorbox}"
                    else:
                        latex += r"\begin{tcolorbox}[colback=success!10,title=Homogeneidade]"
                        latex += r"A distribuição de ruído é consistente em toda a imagem. Nenhuma anomalia estatística significativa foi encontrada."
                        latex += r"\end{tcolorbox}"
                else:
                     latex += r"\textrm{Erro na análise de ruído: " + esc(noise.get('error','')) + r"}"
                
                latex = self._add_refs(latex, "NOISE")


            # --- DCT ANALYSIS (FREQUENCY) ---
            dct_data = None
            if 'image_analysis' in f_analyses:
                dct_data = f_analyses['image_analysis'].get('dct_analysis')
            elif 'dct_analysis' in f_analyses:
                dct_data = f_analyses['dct_analysis']
                
            if dct_data:
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
                
            if cm_data:
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

            # --- DEEPFAKE / FACE FORENSICS ---
            # Busca robusta por chave (pode vir como 'deepfake_analysis' ou 'nome_arquivo_deepfake_analysis')
            df_data = f_analyses.get('deepfake_analysis')
            if not df_data:
                for k, v in f_analyses.items():
                    if str(k).endswith('deepfake_analysis'):
                        df_data = v
                        break

            if df_data:
                df = df_data
                if df.get('status') == 'success':
                    latex += r"\subsection{Análise de Deepfake e Consistência Física}"
                    latex += r"\noindent Verificação de consistência entre sujeito (face/corpo) e fundo, além de busca por artefatos gerativos (GANs)."
                    
                    # Tabela de Resultados
                    latex += r"\begin{table}[H]\centering"
                    latex += r"\begin{tabular}{ll}"
                    latex += r"\toprule \textbf{Métrica} & \textbf{Resultado} \\ \midrule "
                    latex += f"Rostos Detectados & {df.get('detected_faces', 0)} \\\\ "
                    latex += f"Corpos Detectados & {df.get('detected_bodies', 0)} \\\\ "
                    latex += f"Consistência Física (Ruído) & {df.get('consistency_score', 0)}/100 \\\\ "
                    latex += f"Integridade de Frequência (FFT) & {100 - df.get('frequency_score', 0)}/100 \\\\ "
                    latex += f"Naturalidade de Textura (LBP) & {100 - df.get('texture_score', 0)}/100 \\\\ "
                    
                    if df.get('type') == 'video':
                        latex += f"Estabilidade Temporal (Jitter) & {df.get('temporal_jitter', 0)} (Menor é melhor) \\\\ "
                    
                    latex += r"\bottomrule \end{tabular}"
                    latex += r"\caption{Resultados da Análise Forense de Sujeito}"
                    latex += r"\end{table}"
                    
                    # Alertas
                    if df.get('is_suspicious'):
                        latex += r"\begin{tcolorbox}[colback=danger!10,title=ALERTA DE MANIPULAÇÃO]"
                        latex += r"\textbf{Indícios de Deepfake ou Edição detectados:}"
                        latex += r"\begin{itemize}"
                        for det in df.get('details', []):
                            latex += r"\item " + esc(det)
                        latex += r"\end{itemize}"
                        latex += r"\end{tcolorbox}"
                    else:
                        latex += r"\begin{tcolorbox}[colback=success!10,title=Conclusão Preliminar]"
                        latex += r"Nenhum indício óbvio de manipulação generativa (Deepfake) ou inconsistência física grosseira foi detectado nos testes automatizados."
                        latex += r"\end{tcolorbox}"
                else:
                    latex += r"\subsection{Análise de Deepfake e Consistência Física}"
                    latex += r"\begin{tcolorbox}[colback=danger!10,title=Erro na Análise]"
                    latex += esc(df.get('error', 'Erro Desconhecido'))
                    latex += r"\end{tcolorbox}"
                
                latex = self._add_refs(latex, "DEEPFAKE")


            # --- RESAMPLING ANALYSIS (INTERPOLATION) ---
            res_data = None
            if 'image_analysis' in f_analyses:
                res_data = f_analyses['image_analysis'].get('resampling_analysis')
            elif 'resampling_analysis' in f_analyses:
                res_data = f_analyses['resampling_analysis']
                
            if res_data:
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
                
            if jpeg_data:
                jpg = jpeg_data
                ghost_map = jpg.get('map_image')
                is_double = jpg.get('is_double_compression', False)
                est_q = jpg.get('estimated_quality', 0)
                jpg_conc = jpg.get('conclusion', '')
                
                latex += r"\subsection{Análise de Compressão JPEG (Ghosts)}"
                latex += r"\begin{tcolorbox}[colback=lightgray,title=Metodologia]"
                latex += r"Verifica se a imagem foi salva múltiplas vezes em diferentes qualidades. O 'Ghost Map' destaca inconsistências de compressão. Mínimos locais na curva de erro indicam a qualidade original provável."
                latex += r"\end{tcolorbox}"
                
                if jpg.get('status') == 'success':
                    if ghost_map:
                        rel_path = f"../results/{ghost_map}"
                        latex += r"\begin{figure}[H]"
                        latex += r"\centering"
                        latex += f"\\includegraphics[width=0.85\\textwidth]{{{rel_path}}}"
                        latex += r"\caption{Mapa de Fantasmas (" + f"Simulado Q{est_q}" + r")}"
                        latex += r"\end{figure}"
                        
                    latex += r"\noindent\textbf{Resultados:}"
                    latex += r"\begin{itemize}"
                    latex += f"\\item \\textbf{{Status:}} {'Dupla Compressão Detectada' if is_double else 'Padrão Consistente'}"
                    if est_q > 0:
                        latex += f"\\item \\textbf{{Qualidade Original Estimada:}} Q{est_q}"
                    latex += r"\end{itemize}"
                    
                    if is_double:
                        box_col = "danger!10"
                    else:
                        box_col = "success!10"

                    latex += f"\\begin{{tcolorbox}}[colback={box_col},title=Conclusão JPEG]"
                    latex += esc(jpg_conc)
                    latex += r"\end{tcolorbox}"
                else:
                    latex += r"\textrm{Erro JPEG: " + esc(jpg.get('error','')) + r"}"
                
                latex = self._add_refs(latex, "JPEG")


            # --- 7. QUANTIZATION ---
            if 'quantization_analysis' in f_analyses:
                qa = f_analyses['quantization_analysis']
                q_info = qa.get('q_matrix_info', {})
                conc = qa.get('conclusion', '')
                
                latex += r"\subsection{Análise de Quantização (Q-Matrices)}"
                
                if conc:
                    latex += r"\begin{tcolorbox}[colback=white,colframe=primary,title=Assinatura do Encoder]"
                    latex += esc(conc)
                    latex += r"\end{tcolorbox}"
                
                latex += r"\begin{longtable}{p{6cm} p{8cm}}"
                latex += r"\toprule \textbf{Parâmetro} & \textbf{Valor} \\ \midrule "
                
                sps = "Sim" if q_info.get('sps_found') else "Não"
                custom = "Sim" if q_info.get('has_custom_scaling_matrix') else "Não (Padrão/Flat)"
                prof = esc(str(q_info.get('profile_idc', 'N/A')))
                
                # Novos campos
                refs = str(q_info.get('num_ref_frames', 'N/A'))
                entropy = esc(str(q_info.get('entropy_coding', 'N/A')))
                scan = esc(str(q_info.get('scan_type', 'N/A')))
                
                bpp_info = qa.get('bpp_info', {})
                bpp = bpp_info.get('bpp', 0)
                bpp_str = f"{bpp:.3f}" if bpp > 0 else "N/A"
                
                latex += f"Sequence Parameter Set (SPS) & {sps} \\\\ \\hline \n"
                latex += f"Perfil H.264 Detectado & {prof} \\\\ \\hline \n"
                latex += f"Matriz Customizada & {custom} \\\\ \\hline \n"
                latex += f"Quadros de Referência & {refs} \\\\ \\hline \n"
                latex += f"Entropia & {entropy} \\\\ \\hline \n"
                latex += f"Tipo de Scan & {scan} \\\\ \\hline \n"
                latex += f"Bits Per Pixel (BPP) & {bpp_str} \\\\ \\hline \n"
                latex += r"\bottomrule \end{longtable}"

            # --- 8. PRNU INDIVIDUAL ---
            if 'prnu_analysis' in f_analyses:
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
                
            latex += r"\newpage"
        
        # --- 8. PRNU MATRIX (GLOBAL) ---
        prnu_matrix = data.get('prnu_matrix', {})
        if prnu_matrix and 'matrix' in prnu_matrix:
            matrix_data = prnu_matrix['matrix']
            files = prnu_matrix.get('files', [])
            
            if len(files) > 1:
                latex += r"\section{Comparação de Fontes (PRNU) - Matriz de Similaridade}"
                
                latex += r"\begin{tcolorbox}[colback=lightgray,title=Metodologia]"
                latex += r"A correlação cruzada (PCE) compara os ruídos de sensor (fingerprints). Valores altos indicam que os vídeos foram gravados pela mesma câmera."
                latex += r"\begin{itemize}"
                latex += r"\item \textbf{PCE > 60:} Alta probabilidade de mesma origem (Match)."
                latex += r"\end{itemize}"
                latex += r"\end{tcolorbox}"
                
                # Tabela Dinâmica
                # Headers: ID, File, 1, 2, ...
                
                # 1. Legend Table
                latex += r"\subsection*{Legenda dos Arquivos}"
                latex += r"\begin{tabular}{l p{12cm}}"
                latex += r"\toprule \textbf{ID} & \textbf{Arquivo} \\ \midrule "
                for i, fname in enumerate(files):
                    latex += f"{i+1} & {esc(fname)} \\\\ \n"
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
                        if note: pce_str += "*"
                        
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

        latex += r"\end{document}"
        return latex
