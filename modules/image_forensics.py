import cv2
import numpy as np
import json
import os
from pathlib import Path
from core.case_manager import CaseManager
from adapters.ffmpeg_adapter import FFmpegAdapter
from core.hashing import calculate_file_hash
from modules.prnu_analysis import PrnuAnalysisModule

class ImageForensicsModule:
    """
    Módulo de análise forense para imagens estáticas.
    Inclui: Metadados (EXIF/Hash), ELA (Error Level Analysis) e Ruído.
    """
    
    def __init__(self, case_manager: CaseManager, config: dict = None):
        self.cm = case_manager
        self.config = config or {}
        self.logger = self.cm.get_logger()
        self.ffmpeg = FFmpegAdapter(self.logger) # Usado para metadados robustos

    def run(self, input_file: Path, output_filename: str = "image_analysis.json", progress_callback=None):
        self.logger.log("IMG_ANALYSIS_START", {"file": input_file.name})
        
        def notify(msg):
            if progress_callback: progress_callback(msg)

        try:
            # 1. Integridade (Hash)
            notify(f"[{input_file.name}] Calculando Hash e Metadados...")
            file_hash = calculate_file_hash(input_file)
            
            # 2. Metadados (Via FFprobe que suporta imagens bem, ou PIL se necessário)
            # FFprobe é robusto para imagens comuns (JPG, PNG, TIFF)
            metadata = self.ffmpeg.probe_file(input_file)
            
            # 3. ELA - Error Level Analysis
            notify(f"[{input_file.name}] Executando ELA (Error Level Analysis)...")
            ela_result = self._perform_ela(input_file)

            # 4. PRNU Analysis (Sensor Fingerprint)
            notify(f"[{input_file.name}] Extraindo Assinatura de Sensor (PRNU)...")
            prnu_filename = output_filename.replace("image_analysis.json", "prnu.json")
            prnu_module = PrnuAnalysisModule(self.cm)
            prnu_module.frame_limit = 1 
            prnu_result = prnu_module.run(input_file, output_filename=prnu_filename)

            # 5. Noise Consistency Analysis
            notify(f"[{input_file.name}] Analisando Consistência de Ruído Digital...")
            noise_analysis = self._analyze_noise_consistency(input_file)

            # 6. DCT Analysis (Frequency)
            notify(f"[{input_file.name}] Analisando Coeficientes DCT (Frequência)...")
            dct_analysis = self._analyze_dct(input_file)

            # 7. Copy-Move Detection (SIFT)
            notify(f"[{input_file.name}] Detectando Clonagem (Copy-Move SIFT)...")
            copymove_analysis = self._detect_copy_move(input_file)

            # 8. Resampling Analysis (Interpolation)
            notify(f"[{input_file.name}] Buscando Indícios de Interpolação/Resampling...")
            resampling_analysis = self._analyze_resampling(input_file)
            
            # 9. JPEG Ghosts / Double Compression
            notify(f"[{input_file.name}] Varrendo Fantasmas JPEG (Double Compression)...")
            jpeg_analysis = self._analyze_jpeg_compression(input_file)
            
            # 10. Compilar Resultados
            notify(f"[{input_file.name}] Compilando Resultados Forenses...")
            result = {
                "file_hash": file_hash,
                "metadata": metadata,
                "ela_analysis": ela_result,
                "prnu_analysis": prnu_result,
                "noise_analysis": noise_analysis,
                "dct_analysis": dct_analysis,
                "copymove_analysis": copymove_analysis,
                "resampling_analysis": resampling_analysis,
                "jpeg_analysis": jpeg_analysis
            }
            
            out_path = self.cm.results_dir / output_filename
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
                
            self.logger.log("IMG_ANALYSIS_END", {"file": input_file.name})
            return result
            
        except Exception as e:
            self.logger.log("IMG_ANALYSIS_ERROR", {"error": str(e)})
            raise

    def _analyze_jpeg_compression(self, input_file: Path) -> dict:
        """
        Analisa a consistência de compressão JPEG (Double Compression).
        Gera curva de erro para estimar qualidade original e mapa de 'Ghosts'.
        """
        try:
            img = self._read_image_safe(input_file)
            if img is None:
                return {"status": "failed", "error": "Cannot read image"}

            # Se a imagem não for salva com compressão com perdas (ex: PNG), 
            # a análise ainda é válida para saber se VEIO de um JPEG.
            
            # 1. Sweep de Qualidade (60 a 99)
            # Recomprimir e medir erro.
            qualities = list(range(60, 100))
            errors = []
            
            # Usar imagem pequena para o grafico (performance)
            h, w = img.shape[:2]
            scale = 1.0
            if max(h, w) > 1024:
                scale = 1024 / max(h, w)
                small_img = cv2.resize(img, (0,0), fx=scale, fy=scale)
            else:
                small_img = img
            
            temp_path = str(self.cm.results_dir / f"temp_ghost_{input_file.stem}.jpg")
            
            # Lista para guardar desvio padrao normalizado da diferença (métrica comum para Ghost)
            # Ou simplesmente MSE/MAE
            
            for q in qualities:
                # Salvar
                cv2.imwrite(temp_path, small_img, [cv2.IMWRITE_JPEG_QUALITY, q])
                
                # Ler
                # Usar imread direto aqui pois save é local e limpo
                recompressed = cv2.imread(temp_path)
                
                # Calcular Diferença (Diferença absoluta média por canal)
                diff = cv2.absdiff(small_img, recompressed)
                mae = np.mean(diff)
                errors.append(float(mae))
                
            # Clean
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
            # 2. Analisar Curva de Erro
            # Procurar minimos locais. O mínimo em 98/99 é trivial (alta qualidade).
            # Procuramos um "dip" anterior, ex: quality 75.
            
            minima = []
            # Smooth curve slightly?
            # Find valleys
            predicted_q = 0
            
            # Derivada simples
            # valley se errors[i-1] > errors[i] < errors[i+1]
            for i in range(1, len(errors)-1):
                if errors[i-1] > errors[i] and errors[i] < errors[i+1]:
                    q_val = qualities[i]
                    minima.append(q_val)
            
            # O último mínimo costuma ser a qualidade atual (se for jpeg).
            # Um mínimo ANTERIOR indica double compression.
            
            is_double = False
            primary_q = 0
            
            if len(minima) > 0:
                # Assumimos que o maior Q é o atual (aproximadamente)
                current_q_est = max(minima)
                
                # Se tiver outro min significativo, é double
                # Filtrar minimos muito proximos
                valid_minima = [m for m in minima if m < 95] # Ignore very high default
                
                if len(valid_minima) > 1:
                    is_double = True
                    primary_q = valid_minima[0] # O menor/primeiro
                    conclusion = f"Alta probabilidade de Dupla Compressão. Qualidade original estimada: Q{primary_q}."
                elif len(valid_minima) == 1:
                     primary_q = valid_minima[0]
                     conclusion = f"Compressão Simples detectada. Qualidade estimada: Q{primary_q}."
                else:
                     conclusion = "Padrão de compressão inconclusivo (possível PNG/Lossless ou Q muito alta)."
            else:
                conclusion = "Nenhum padrão de compressão claro (Gráfico monotônico)."

            # 3. Gerar Mapa de Ghosts (NAg - Noise Artifacts of ghosts)
            # Diferença entre Imagem e JPEG Quality(Primary)
            # Usar a qualidade estimada (ou uma qualidade de contraste padrão, ex: 75, se não achou nada)
            target_q = primary_q if primary_q > 0 else 75
            
            # Recomprimir imagem FULL SIZE na target_q
            temp_path_full = str(self.cm.results_dir / f"temp_ghost_full_{input_file.stem}.jpg")
            cv2.imwrite(temp_path_full, img, [cv2.IMWRITE_JPEG_QUALITY, target_q])
            recomp_full = cv2.imread(temp_path_full)
            if os.path.exists(temp_path_full): os.remove(temp_path_full)
            
            # Mapa de Diferença Médio (Ghost Map)
            diff_full = cv2.absdiff(img, recomp_full)
            # Converter p/ grayscale média
            diff_gray = np.mean(diff_full, axis=2).astype(np.uint8)
            
            # Normalizar para visualização (Contrast Stretch)
            # Para ghosts, suavizar ajuda a ver manchas
            diff_blur = cv2.GaussianBlur(diff_gray, (7,7), 0)
            norm_ghost = cv2.normalize(diff_blur, None, 0, 255, cv2.NORM_MINMAX)
            heatmap = cv2.applyColorMap(norm_ghost.astype(np.uint8), cv2.COLORMAP_JET)
            
            ghost_filename = f"{input_file.stem}_ghost_map_q{target_q}.jpg"
            ghost_path = self.cm.results_dir / ghost_filename
            self._write_image_safe(ghost_path, heatmap)

            return {
                "status": "success",
                "is_double_compression": is_double,
                "estimated_quality": int(primary_q),
                "quality_minima": minima,
                "map_image": ghost_filename,
                "conclusion": conclusion
            }

        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _analyze_resampling(self, input_file: Path) -> dict:
        """
        Detecta indícios de resampling (redimensionamento/rotação) buscando 
        periodicidade nos artefatos de interpolação via FFT local no resíduo linear.
        """
        try:
            img = self._read_image_safe(input_file)
            if img is None:
                return {"status": "failed", "error": "Cannot read image"}

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape
            
            # 1. Calcular Resíduo Linear (2ª Derivada aproximada)
            # Remove o conteúdo da imagem para deixar apenas o ruído/artefatos high-freq.
            # Kernel Laplaciano simples
            kernel = np.array([[0, -1, 0], 
                               [-1, 4, -1], 
                               [0, -1, 0]], dtype=np.float32)
            
            residual = cv2.filter2D(gray.astype(np.float32), -1, kernel)
            
            # 2. Análise Espectral por Blocos (Métrica de Periodicidade)
            block_size = 64
            prob_map = np.zeros((h, w), dtype=np.float32)
            
            p_scores = []
            
            # Iterar blocos
            for y in range(0, h, block_size):
                for x in range(0, w, block_size):
                    y_end = min(y + block_size, h)
                    x_end = min(x + block_size, w)
                    
                    # Se bloco for muito pequeno, ignora
                    if (x_end-x) < 32 or (y_end-y) < 32: continue
                    
                    block = residual[y:y_end, x:x_end]
                    
                    # FFT 2D
                    f = np.fft.fft2(block)
                    fshift = np.fft.fftshift(f)
                    magnitude = np.abs(fshift)
                    
                    # Zerar o centro (DC component e baixas freq content remanescente)
                    cy, cx = magnitude.shape[0]//2, magnitude.shape[1]//2
                    # Zerar vizinhança imediata do DC (3x3)
                    magnitude[cy-2:cy+3, cx-2:cx+3] = 0
                    
                    # Métrica: Pico vs Média (Peak-to-Average Ratio)
                    # Um bloco resampled tem picos claros de aliasing.
                    mean_mag = np.mean(magnitude)
                    max_mag = np.max(magnitude)
                    
                    if mean_mag == 0: 
                        score = 0
                    else:
                        score = max_mag / mean_mag
                        
                    p_scores.append(score)
                    prob_map[y:y_end, x:x_end] = score

            # Estatísticas
            global_mean = np.mean(p_scores) if p_scores else 0
            
            # Visualização
            # Normalizar para 0-255
            # Scores tipicos: < 10 (normal), > 15-20 (resampled)
            # Vamos saturar em 30 para visualização
            vis_map = np.clip(prob_map * (255.0/30.0), 0, 255).astype(np.uint8)
            heatmap = cv2.applyColorMap(vis_map, cv2.COLORMAP_JET)
            
            res_filename = f"{input_file.stem}_resampling_map.jpg"
            res_path = self.cm.results_dir / res_filename
            self._write_image_safe(res_path, heatmap)
            
            # Conclusão
            conc = "Baixa probabilidade de resampling detectada."
            # Contar blocos suspeitos (> 15 score)
            suspicious_blocks = sum(1 for s in p_scores if s > 15)
            ratio = suspicious_blocks / len(p_scores) if p_scores else 0
            
            if ratio > 0.3:
                 conc = f"ALTA PROBABILIDADE: {ratio*100:.1f}% da imagem apresenta fortes traços de redimensionamento/rotação."
            elif ratio > 0.05:
                 conc = f"Indícios de manipulação: {suspicious_blocks} blocos com periodicidade suspeita detectados."

            return {
                "status": "success",
                "map_image": res_filename,
                "global_periodicity_score": float(global_mean),
                "suspicious_blocks_ratio": float(ratio),
                "conclusion": conc
            }
            
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _detect_copy_move(self, input_file: Path) -> dict:
        """
        Detecta clonagem (Copy-Move) usando correspondência de keypoints SIFT.
        Identifica regiões duplicadas robustas a rotação e escala.
        """
        try:
            img = self._read_image_safe(input_file)
            if img is None:
                return {"status": "failed", "error": "Cannot read image"}

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # 1. Detectar SIFT Features
            n_feats = int(self.config.get('copymove_features', 2000))
            sift = cv2.SIFT_create(nfeatures=n_feats) # Limitar features para performance
            keypoints, descriptors = sift.detectAndCompute(gray, None)
            
            if descriptors is None or len(keypoints) < 5:
                return {"status": "insufficient_features", "matches_found": 0}
            
            # 2. Matching (Brute Force KNN)
            bf = cv2.BFMatcher()
            matches = bf.knnMatch(descriptors, descriptors, k=10) 
            
            initial_matches = []
            min_dist_spatial = 50.0 
            
            for m_list in matches:
                for m in m_list:
                    if m.queryIdx == m.trainIdx: continue 
                    
                    p1 = keypoints[m.queryIdx].pt
                    p2 = keypoints[m.trainIdx].pt
                    dist_spatial = np.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)
                    
                    # Stricter descriptor distance (typ 0-500, 150 is loose, try 100)
                    if dist_spatial > min_dist_spatial and m.distance < 120:
                         initial_matches.append(m)

            # 3. Filtragem por Coerência (Clustering de Vetores)
            # Uma cópia real terá vários keypoints se movendo na mesma direção e distância.
            # Ruído aleatório (cabelo, grama) terá direções caóticas.
            
            coherent_matches = []
            if initial_matches:
                # Calcular vetor de deslocamento (dx, dy) para cada match
                vectors = []
                for m in initial_matches:
                    p1 = np.array(keypoints[m.queryIdx].pt)
                    p2 = np.array(keypoints[m.trainIdx].pt)
                    vec = p2 - p1
                    angle = np.arctan2(vec[1], vec[0])
                    length = np.linalg.norm(vec)
                    vectors.append({'m': m, 'ang': angle, 'len': length})

                # Clusterizar vetores similares
                # Tolerância: 15 graus (0.26 rad) e 10% de diferença de comprimento
                final_selection = []
                
                # Otimização simples: binning ou loop O(N^2) no subset já filtrado
                # Como 'initial_matches' já é filtrado, N deve ser pequeno (<1000).
                
                used_indices = set()
                min_cluster_size = int(self.config.get('copymove_min_cluster', 4)) # Mínimo de pontos concordantes para validar a cópia
                
                for i in range(len(vectors)):
                    if i in used_indices: continue
                    
                    v_ref = vectors[i]
                    cluster = [v_ref]
                    
                    for j in range(i+1, len(vectors)):
                        if j in used_indices: continue
                        
                        v_test = vectors[j]
                        
                        # Diff Angular (considerando prob ciclica)
                        diff_ang = abs(v_ref['ang'] - v_test['ang'])
                        if diff_ang > np.pi: diff_ang = 2*np.pi - diff_ang
                        
                        # Diff Comprimento
                        len_ratio = abs(v_ref['len'] - v_test['len']) / (v_ref['len'] + 1e-6)
                        
                        if diff_ang < 0.2 and len_ratio < 0.15:
                            cluster.append(v_test)
                            
                    # Se cluster for grande o suficiente, aceita todos
                    if len(cluster) >= min_cluster_size:
                        for item in cluster:
                            final_selection.append(item['m'])
                            # Marcar indices como usados (simplificação, ideal seria não marcar para permitir overlaps, mas evita duplicatas)
                            
                unique_matches = []
                seen_pairs = set()
                for m in final_selection:
                    pair = tuple(sorted((m.queryIdx, m.trainIdx)))
                    if pair not in seen_pairs:
                        seen_pairs.add(pair)
                        unique_matches.append(m)
            else:
                unique_matches = []
                    
            # Visualização
            vis_img = img.copy()
            # Draw lines
            for m in unique_matches:
                p1 = tuple(map(int, keypoints[m.queryIdx].pt))
                p2 = tuple(map(int, keypoints[m.trainIdx].pt))
                cv2.line(vis_img, p1, p2, (0, 255, 255), 1)
                cv2.circle(vis_img, p1, 3, (0, 0, 255), -1)
                cv2.circle(vis_img, p2, 3, (0, 0, 255), -1)
                
            # Salvar
            cm_filename = f"{input_file.stem}_copymove_map.jpg"
            cm_path = self.cm.results_dir / cm_filename
            self._write_image_safe(cm_path, vis_img)
            
            count = len(unique_matches)
            
            # Conclusão
            conc = "Nenhuma duplicação óbvia detectada."
            if count > 10:
                conc = f"ALTO RISCO: {count} pares de regiões idênticas detectadas. Possível clonagem."
            elif count > 0:
                conc = f"Atenção: {count} pares suspeitos encontrados. Verifique padrões repetitivos."

            return {
                "status": "success",
                "matches_found": count,
                "map_image": cm_filename,
                "conclusion": conc
            }

        except Exception as e:
             return {"status": "error", "error": str(e)}

    def _analyze_dct(self, input_file: Path) -> dict:
        """
        Analisa os coeficientes DCT (Discrete Cosine Transform) em blocos de 8x8.
        Detecta anomalias na distribuição de frequência (indicativo de recompressão ou copy-move).
        """
        try:
            img = self._read_image_safe(input_file)
            if img is None:
                return {"status": "failed", "error": "Cannot read image"}
                
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape
            
            # Pad to 8x8 multiple
            pad_h = (8 - h % 8) % 8
            pad_w = (8 - w % 8) % 8
            if pad_h > 0 or pad_w > 0:
                gray = cv2.copyMakeBorder(gray, 0, pad_h, 0, pad_w, cv2.BORDER_REFLECT)
                
            h_pad, w_pad = gray.shape
            gray_f = gray.astype(np.float32)
            
            # Mapas de Energia
            energy_map = np.zeros((h_pad // 8, w_pad // 8), dtype=np.float32)
            
            block_stats = []
            
            # Processar blocos 8x8
            for y in range(0, h_pad, 8):
                for x in range(0, w_pad, 8):
                    block = gray_f[y:y+8, x:x+8]
                    
                    # Compute DCT
                    dct_block = cv2.dct(block)
                    
                    # AC Energy (Sum of abs coefficients, ignoring DC at [0,0])
                    # DC coefficient is the mean, we want texture/frequency energy
                    ac_energy = np.sum(np.abs(dct_block)) - np.abs(dct_block[0,0])
                    
                    energy_map[y//8, x//8] = ac_energy
                    block_stats.append(ac_energy)
                    
            # Analisar Estatísticas Globais dos Blocos
            mean_energy = np.mean(block_stats)
            std_energy = np.std(block_stats)
            
            # Validar se std é zero (imagem flat)
            if std_energy == 0: std_energy = 1e-6
            
            # Detectar Outliers (Blocos com energia muito diferente da média global ou local)
            # Para visualização, normalizar o mapa
            norm_map = cv2.normalize(energy_map, None, 0, 255, cv2.NORM_MINMAX)
            norm_map_uint8 = norm_map.astype(np.uint8)
            
            # Resize para tamanho original para visualização
            dct_vis = cv2.resize(norm_map_uint8, (w, h), interpolation=cv2.INTER_NEAREST)
            dct_heatmap = cv2.applyColorMap(dct_vis, cv2.COLORMAP_INFERNO)
            
            # Salvar
            dct_filename = f"{input_file.stem}_dct_map.jpg"
            dct_path = self.cm.results_dir / dct_filename
            self._write_image_safe(dct_path, dct_heatmap)
            
            return {
                "status": "success",
                "map_image": dct_filename,
                "global_stats": {
                    "mean_ac_energy": float(mean_energy),
                    "std_ac_energy": float(std_energy)
                },
                "conclusion": "Análise de frequência DCT concluída. Verifique o mapa para descontinuidades de textura."
            }
            
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _analyze_noise_consistency(self, input_file: Path, block_size: int = 64) -> dict:
        """
        Analisa a consistência do ruído digital dividindo a imagem em blocos.
        Calcula Variância, Desvio Padrão e Entropia do resíduo de ruído para cada bloco.
        """
        try:
            img = self._read_image_safe(input_file)
            if img is None:
                return {"status": "failed", "error": "Cannot read image"}

            # Converter para Grayscale
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # Extrair Resíduo de Ruído Estimado (High Pass Filter)
            # Uma técnica simples é subtrair uma versão suavizada (filtro de mediana)
            # Para evitar bordas fortes influenciando demais, usamos um filtro mediano que preserva bordas melhor que gaussian.
            denoised = cv2.medianBlur(gray, 3)
            noise_residual = cv2.absdiff(gray, denoised)
            
            h, w = noise_residual.shape
            
            # Estatísticas por Bloco
            block_stats = []
            map_vis = np.zeros((h, w), dtype=np.uint8)
            
            variances = []
            entropies = []
            
            # Iterar blocos
            for y in range(0, h, block_size):
                for x in range(0, w, block_size):
                    # Definir ROI do bloco
                    y_end = min(y + block_size, h)
                    x_end = min(x + block_size, w)
                    block = noise_residual[y:y_end, x:x_end]
                    
                    if block.size == 0: continue
                    
                    # Calcular métricas
                    var = np.var(block)
                    std = np.std(block)
                    ent = self._calc_entropy(block)
                    
                    variances.append(var)
                    entropies.append(ent)
                    
                    block_stats.append({
                        "x": x, "y": y,
                        "variance": float(var),
                        "std_dev": float(std),
                        "entropy": float(ent)
                    })
                    
                    # Preencher visualização (Normalizado pela variância local)
                    # Vamos preencher o bloco no mapa visual com um valor representativo (std dev escalado)
                    # Cap visual em 255
                    vis_val = min(int(std * 10), 255) 
                    map_vis[y:y_end, x:x_end] = vis_val

            # Análise Global e Outliers
            global_var_mean = np.mean(variances)
            global_var_std = np.std(variances)
            
            outliers = []
            threshold_z = 3.0 # Limite de desvios padrão para considerar anomalia
            
            for b in block_stats:
                z_score = (b['variance'] - global_var_mean) / (global_var_std + 1e-6)
                if abs(z_score) > threshold_z:
                    outliers.append(b)
            
            # Gerar Mapa de Calor Colorido (JET)
            heatmap_color = cv2.applyColorMap(map_vis, cv2.COLORMAP_JET)
            
            # Salvar Mapa
            map_filename = f"{input_file.stem}_noise_map.jpg"
            map_path = self.cm.results_dir / map_filename
            self._write_image_safe(map_path, heatmap_color)
            
            return {
                "status": "success",
                "map_image": map_filename,
                "block_size": block_size,
                "total_blocks": len(block_stats),
                "global_stats": {
                    "mean_variance": float(global_var_mean),
                    "std_variance": float(global_var_std),
                    "mean_entropy": float(np.mean(entropies))
                },
                "outliers_detected": len(outliers),
                "conclusion": "Regiões com desvio de ruído > 3 sigma detectadas." if outliers else "Distribuição de ruído homogênea (dentro dos parâmetros estatísticos)."
            }

        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _calc_entropy(self, image_block):
        """Calcula entropia de Shannon para um bloco de imagem (uint8)."""
        # Calcular histograma
        counts = np.bincount(image_block.flatten(), minlength=256)
        # Probabilidades
        p = counts / counts.sum()
        p = p[p > 0] # Remover zeros para log
        ent = -np.sum(p * np.log2(p))
        return ent

    def _read_image_safe(self, path: Path):
        """Lê imagem suportando caracteres especiais no path (Windows)."""
        # OpenCV imread falha com acentos no Windows.
        # Solução: Ler bytes com numpy e decodificar.
        try:
            data = np.fromfile(str(path), dtype=np.uint8)
            img = cv2.imdecode(data, cv2.IMREAD_COLOR)
            return img
        except Exception:
            return None

    def _write_image_safe(self, path: Path, img, params=None):
        """Salva imagem suportando caracteres especiais."""
        try:
            ext = path.suffix
            result, enc_img = cv2.imencode(ext, img, params)
            if result:
                with open(path, 'wb') as f:
                    enc_img.tofile(f)
            return result
        except Exception:
            return False

    def _perform_ela(self, input_file: Path) -> dict:
        """Gera imagem ELA (Error Level Analysis) comparando com compressão JPEG."""
        try:
            # Ler imagem original
            orig = self._read_image_safe(input_file)
            if orig is None:
                return {"status": "failed", "error": f"Cannot read image: {input_file.name}"}
            
            # Caminho temp para recompressão
            temp_jpg = self.cm.results_dir / f"temp_ela_{input_file.stem}.jpg"
            
            # Salvar com compressão JPEG (Qualidade 90-95 é padrão para ELA)
            self._write_image_safe(temp_jpg, orig, [cv2.IMWRITE_JPEG_QUALITY, 90])
            
            # Ler imagem recomprimida
            compressed = self._read_image_safe(temp_jpg)
            
            # Calcular diferença absoluta (Ruído de compressão perdido)
            diff = cv2.absdiff(orig, compressed)
            
            # Remover temp
            temp_jpg.unlink(missing_ok=True)
            
            # Amplificar a diferença para visualização (Scale)
            # Valor típico: multiplicar por 10 ou 20.
            # Convert to float to avoid saturation early
            diff_float = diff.astype(np.float32)
            
            # Amplificação Base
            ela_image = diff_float * 15.0 
            
            # Auto-Brightness para Visualização
            # Se a imagem for muito escura (alta qualidade), normalizamos para tornar o padrão visível.
            max_val = np.max(ela_image)
            if max_val > 0 and max_val < 255:
                # Escalar para ocupar o range 0-255 (Dynamic Range Compression)
                ela_display = (ela_image / max_val) * 255.0
                ela_display = ela_display.astype(np.uint8)
            else:
                ela_display = np.clip(ela_image, 0, 255).astype(np.uint8)
            
            # Métrica com base no erro absoluto ORIGINAL (sem normalização visual)
            # Isso é importante para comparar qualidade real.
            ela_score = np.mean(diff_float)
            
            # Salvar imagem ELA (Mapa de Calor Visual)
            ela_filename = f"{input_file.stem}_ela_heatmap.jpg"
            ela_path = self.cm.results_dir / ela_filename
            self._write_image_safe(ela_path, ela_display)
            
            # Interpretação Dinâmica
            interpretation = "Resultados ELA: "
            if ela_score < 2.0:
                interpretation += f"Erro médio muito baixo ({ela_score:.2f}). Imagem de alta qualidade ou salva com compressão mínima. O mapa de calor foi amplificado para revelar padrões sutis."
            elif ela_score > 10.0:
                interpretation += f"Erro médio alto ({ela_score:.2f}). Imagem com muita compressão ou re-salvamentos múltiplos."
            else:
                interpretation += f"Nível de erro padrão ({ela_score:.2f}). Verifique regiões brilhantes que destoam do fundo."
            
            return {
                "status": "success",
                "ela_image": ela_filename,
                "ela_score": float(ela_score),
                "amplification_factor": "Auto-Scale",
                "interpretation": interpretation
            }
            
        except Exception as e:
            return {"status": "error", "error": str(e)}
