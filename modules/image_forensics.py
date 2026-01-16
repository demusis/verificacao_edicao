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

            # JPEG Ghosts / Double Compression Analysis
            # Baseado em Farid (2009): "Exposing Digital Forgeries From JPEG Ghosts".
            # O princípio é que se uma imagem foi comprimida em uma qualidade Q1 e depois 
            # re-salva em Q2, a diferença entre a imagem re-salva e versões originais terá 
            # um 'mínimo local' (dip) no ponto Q1.
            
            # 1. Sweep de Qualidade (60 a 99)
            # Recomprimir a imagem em diversos graus e medir o erro residual.
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
                
                # Verificar se leitura foi bem sucedida
                if recompressed is None or recompressed.shape != small_img.shape:
                    continue  # Skipar esta qualidade se falhar
                
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
                # O Fator Q (Quality) escala as matrizes de quantização JPEG (1-100).
                # Um mínimo detectado em Q63 indica que a imagem possui assinaturas 
                # de quantização de um salvamento anterior nesta qualidade específica.
                
                current_q_est = max(minima)
                valid_minima = [m for m in minima if m < 95] 
                
                if len(valid_minima) > 1:
                    is_double = True
                    primary_q = valid_minima[0] # Provável qualidade original
                    conclusion = f"Alta probabilidade de Dupla Compressão. Qualidade Original Estimada: Q{primary_q}. (Indica que a imagem foi editada/re-salva após este ponto)."
                elif len(valid_minima) == 1:
                     primary_q = valid_minima[0]
                     conclusion = f"Compressão Simples detectada. Qualidade atual estimada: Q{primary_q}."
                else:
                     conclusion = "Padrão de compressão inconclusivo. Q elevado (>95) ou formato original sem perda (PNG/TIFF)."
            else:
                conclusion = "Nenhum padrão de compressão múltipla claro. Gráfico de erro monotônico."

            # 3. Gerar Mapa de Ghosts (NAg - Noise Artifacts of ghosts)
            # Diferença entre Imagem e JPEG Quality(Primary)
            # Usar a qualidade estimada (ou uma qualidade de contraste padrão, ex: 75, se não achou nada)
            target_q = primary_q if primary_q > 0 else 75
            
            # Recomprimir imagem FULL SIZE na target_q
            temp_path_full = str(self.cm.results_dir / f"temp_ghost_full_{input_file.stem}.jpg")
            cv2.imwrite(temp_path_full, img, [cv2.IMWRITE_JPEG_QUALITY, target_q])
            recomp_full = cv2.imread(temp_path_full)
            if os.path.exists(temp_path_full): os.remove(temp_path_full)
            
            # Verificar se leitura foi bem sucedida
            if recomp_full is None or recomp_full.shape != img.shape:
                return {"status": "error", "error": "Failed to read recompressed image for ghost map."}
            
            # Mapa de Diferença Médio (Ghost Map)
            diff_full = cv2.absdiff(img, recomp_full)
            # Converter p/ grayscale média
            diff_gray = np.mean(diff_full, axis=2).astype(np.uint8)
            
            # Normalizar para visualização (Contrast Stretch)
            # Para ghosts, suavizar ajuda a ver manchas
            diff_blur = cv2.GaussianBlur(diff_gray, (7,7), 0)
            norm_ghost = cv2.normalize(diff_blur, None, 0, 255, cv2.NORM_MINMAX)
            heatmap = cv2.applyColorMap(norm_ghost.astype(np.uint8), cv2.COLORMAP_JET)
            
            # Pegar valores reais antes da normalização para a legenda
            real_min = float(np.min(diff_blur))
            real_max = float(np.max(diff_blur))
            heatmap_with_legend = self._add_colorbar(heatmap, cv2.COLORMAP_JET, "Baixo Erro", "Alto Erro", real_min, real_max)
            
            ghost_filename = f"{input_file.stem}_ghost_map_q{target_q}.jpg"
            ghost_path = self.cm.results_dir / ghost_filename
            self._write_image_safe(ghost_path, heatmap_with_legend)

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
            heatmap_with_legend = self._add_colorbar(heatmap, cv2.COLORMAP_JET, "Normal", "Resampled", 0.0, 30.0)
            
            res_filename = f"{input_file.stem}_resampling_map.jpg"
            res_path = self.cm.results_dir / res_filename
            self._write_image_safe(res_path, heatmap_with_legend)
            
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
            
            # 2. Matching (Brute Force KNN) com Lowe's Ratio Test
            # Como casamos descriptors contra SI MESMOS, o melhor match (k=0) é o próprio ponto (dist=0).
            # Precisamos do 2º e 3º melhores matches para o ratio test.
            bf = cv2.BFMatcher()
            matches = bf.knnMatch(descriptors, descriptors, k=3) 
            
            initial_matches = []
            min_dist_spatial = 50.0 
            ratio_threshold = 0.75 # Lowe's Ratio Test (típico 0.7 a 0.8)
            
            for m_list in matches:
                if len(m_list) < 3: continue
                
                # m_list[0] = auto-match (dist 0)
                # m_list[1] = melhor candidato
                # m_list[2] = segundo melhor candidato
                m1 = m_list[1]
                m2 = m_list[2]
                
                if m1.distance < ratio_threshold * m2.distance:
                    p1 = keypoints[m1.queryIdx].pt
                    p2 = keypoints[m1.trainIdx].pt
                    dist_spatial = np.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)
                    
                    # Filtro de distância espacial e descritora absoluta
                    if dist_spatial > min_dist_spatial and m1.distance < 110:
                         initial_matches.append(m1)

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
                    cluster_indices = [i]
                    
                    for j in range(i+1, len(vectors)):
                        if j in used_indices: continue
                        
                        v_test = vectors[j]
                        
                        # Diff Angular (considerando prob ciclica)
                        diff_ang = abs(v_ref['ang'] - v_test['ang'])
                        if diff_ang > np.pi: diff_ang = 2*np.pi - diff_ang
                        
                        # Diff Comprimento
                        len_ratio = abs(v_ref['len'] - v_test['len']) / (v_ref['len'] + 1e-6)
                        
                        # Tolerâncias mais estritas (0.15 rad ~ 8 graus)
                        if diff_ang < 0.15 and len_ratio < 0.12:
                            cluster_indices.append(j)
                            
                    # Se cluster for grande o suficiente, aceita todos
                    if len(cluster_indices) >= min_cluster_size:
                        for idx in cluster_indices:
                            final_selection.append(vectors[idx]['m'])
                            used_indices.add(idx)
                            
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
            if count >= 15:
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
            dct_with_legend = self._add_colorbar(dct_heatmap, cv2.COLORMAP_INFERNO, "Baixa Freq", "Alta Freq", 0.0, 50.0)
            
            # Salvar
            dct_filename = f"{input_file.stem}_dct_map.jpg"
            dct_path = self.cm.results_dir / dct_filename
            self._write_image_safe(dct_path, dct_with_legend)
            
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
            # Mapa de variâncias em float para normalização posterior
            map_float = np.zeros((h, w), dtype=np.float32)
            
            variances = []
            entropies = []
            std_values = []
            
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
                    std_values.append(std)
                    
                    block_stats.append({
                        "x": x, "y": y,
                        "variance": float(var),
                        "std_dev": float(std),
                        "entropy": float(ent)
                    })
                    
                    # Preencher mapa float com valor de std (será normalizado depois)
                    map_float[y:y_end, x:x_end] = std

            # Análise Global e Outliers
            global_var_mean = np.mean(variances) if variances else 0
            global_var_std = np.std(variances) if variances else 0
            
            outliers = []
            threshold_z = 3.0 # Limite de desvios padrão para considerar anomalia
            
            for b in block_stats:
                z_score = (b['variance'] - global_var_mean) / (global_var_std + 1e-6)
                if abs(z_score) > threshold_z:
                    outliers.append(b)
            
            # Normalizar mapa para 0-255 usando min-max (usa range completo da imagem)
            # Isso garante que QUALQUER diferença seja visível, mesmo em imagens de baixo ruído
            min_val = np.min(map_float)
            max_val = np.max(map_float)
            
            if max_val - min_val > 1e-6:
                # Normalização min-max para ocupar todo o range visual
                map_normalized = ((map_float - min_val) / (max_val - min_val) * 255).astype(np.uint8)
            else:
                # Imagem completamente uniforme (sem variação de ruído)
                map_normalized = np.full((h, w), 128, dtype=np.uint8)
            
            # Gerar Mapa de Calor Colorido (JET)
            heatmap_color = cv2.applyColorMap(map_normalized, cv2.COLORMAP_JET)
            
            # Adicionar escala de cores (Legenda)
            heatmap_with_legend = self._add_colorbar(heatmap_color, cv2.COLORMAP_JET, "Ruido Baixo", "Ruido Alto", min_val, max_val)
            
            # Salvar Mapa
            map_filename = f"{input_file.stem}_noise_map.jpg"
            map_path = self.cm.results_dir / map_filename
            self._write_image_safe(map_path, heatmap_with_legend)
            
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
        """
        Gera imagem ELA (Error Level Analysis) comparando com compressão JPEG.
        
        Princípio Científico:
        O ELA identifica áreas da imagem com diferentes níveis de compressão. Imagens digitais
        não manipuladas tendem a atingir um "estado estável" (steady state) onde a recompressão
        em uma qualidade similar gera um erro uniforme. Edições posteriores "resetam" esse estado,
        fazendo com que regiões manipuladas apresentem níveis de erro distintos do restante.
        
        Referências:
        - Krawetz, N. (2007). "A Picture's Worth: Digital Image Analysis and Forensics".
        - Farid, H. (2009). "Exposing Digital ForgeriesFrom JPEG Ghosts".
        """
        try:
            # Ler imagem original
            orig = self._read_image_safe(input_file)
            if orig is None:
                return {"status": "failed", "error": f"Cannot read image: {input_file.name}"}
            
            # Caminho temp para recompressão - usar diretório temporário do sistema para evitar problemas de path
            import tempfile
            temp_dir = tempfile.gettempdir()
            # Usar nome simples sem caracteres especiais
            temp_jpg_path = Path(temp_dir) / f"ela_temp_{id(self)}.jpg"
            
            # Salvar com compressão JPEG (Qualidade 90-95 é padrão para ELA)
            write_success = self._write_image_safe(temp_jpg_path, orig, [cv2.IMWRITE_JPEG_QUALITY, 90])
            
            if not write_success:
                return {"status": "error", "error": f"Failed to write temp JPEG for ELA to {temp_jpg_path}"}
            
            # Verificar se arquivo foi criado
            if not temp_jpg_path.exists():
                return {"status": "error", "error": f"Temp JPEG was not created at {temp_jpg_path}"}
            
            # Ler imagem recomprimida
            compressed = self._read_image_safe(temp_jpg_path)
            
            # Verificar se leitura foi bem sucedida
            if compressed is None:
                temp_jpg_path.unlink(missing_ok=True)
                return {"status": "error", "error": f"Failed to read recompressed JPEG for ELA from {temp_jpg_path}"}
            
            # Verificar se dimensões são compatíveis
            if compressed.shape != orig.shape:
                temp_jpg_path.unlink(missing_ok=True)
                return {"status": "error", "error": f"Dimension mismatch: original {orig.shape} vs compressed {compressed.shape}"}
            
            # Calcular diferença absoluta (Ruído de compressão perdido)
            diff = cv2.absdiff(orig, compressed)
            
            # Remover temp
            temp_jpg_path.unlink(missing_ok=True)
            
            # Amplificar a diferença para visualização (Scale)
            # Valor típico: multiplicar por 10 ou 20.
            # Convert to float to avoid saturation early
            diff_float = diff.astype(np.float32)
            
            # Amplificação Base
            ela_image = diff_float * 15.0 
            
            # Métrica: Score de Diferença Global (Global Difference Score)
            # Representa o Erro Médio Absoluto (MAE) por pixel/canal.
            ela_score = np.mean(diff_float)
            
            # --- NOVIDADE: Gerar Mapa de Calor (JET) para consistência visual ---
            # Converter diferença BGR para média de intensidade
            ela_gray = np.mean(diff_float, axis=2).astype(np.float32)
            
            # Normalização para visualização
            max_err = np.max(ela_gray)
            if max_err > 1e-6:
                ela_norm = (ela_gray / max_err * 255).astype(np.uint8)
            else:
                ela_norm = np.zeros_like(ela_gray, dtype=np.uint8)
                
            ela_heatmap = cv2.applyColorMap(ela_norm, cv2.COLORMAP_JET)
            
            # Adicionar Legenda
            # val_max é o erro absoluto máximo encontrado
            ela_with_legend = self._add_colorbar(ela_heatmap, cv2.COLORMAP_JET, "Erro Local Baixo", "Erro Local Alto", 0.0, float(max_err))
            
            # Salvar imagem ELA (Mapa de Calor Visual)
            ela_filename = f"{input_file.stem}_ela_heatmap.jpg"
            ela_path = self.cm.results_dir / ela_filename
            self._write_image_safe(ela_path, ela_with_legend)
            
            # Interpretação Dinâmica (Baseada em parâmetros forenses)
            interpretation = "Interpretando Score de Diferença Global (MAE): "
            if ela_score < 2.0:
                interpretation += f"Erro muito baixo ({ela_score:.2f}). Imagem de alta qualidade ou salva no 'steady state' (Q95-100). Pequenas heterogeneidades podem ser ruído natural."
            elif ela_score < 5.0:
                interpretation += f"Faixa típica ({ela_score:.2f}). Comportamento esperado para imagens JPEG originais (Q80-95). Verifique inconsistências locais."
            elif ela_score <= 10.0:
                interpretation += f"Erro elevado ({ela_score:.2f}). Indica compressão moderada ou duplo salvamento. Regiões de alta frequência (bordas) tendem a brilhar mais."
            else:
                interpretation += f"Erro crítico ({ela_score:.2f}). Imagem com compressão agressiva ou múltiplos ciclos de re-processamento (geração profunda)."
            
            interpretation += "\nNOTA: Foque na heterogeneidade espacial: regiões manipuladas brilham de forma diferente do fundo original."
            
            return {
                "status": "success",
                "ela_image": ela_filename,
                "ela_score": float(ela_score),
                "amplification_factor": "Auto-Scale",
                "interpretation": interpretation
            }
            
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _add_colorbar(self, img, colormap=cv2.COLORMAP_JET, label_min="Baixo", label_max="Alto", val_min=None, val_max=None):
        """Adiciona uma legenda com valores numéricos, largura dinâmica e posicionamento preciso."""
        try:
            h, w = img.shape[:2]
            
            # Formatar labels com valores se existirem
            txt_max = str(label_max)
            txt_min = str(label_min)
            if val_max is not None:
                txt_max += f" ({val_max:.1f})"
            if val_min is not None:
                txt_min += f" ({val_min:.1f})"
                
            # Parâmetros de layout base
            bar_w = 30
            v_margin = 50
            h_margin = 15
            left_offset = 15
            
            font = cv2.FONT_HERSHEY_SIMPLEX
            # Escala dinâmica baseada na altura da imagem
            f_scale = max(0.4, min(1.0, h / 900.0))
            thickness = 1 if f_scale < 0.8 else 2
            color = (30, 30, 30) # Cinza escuro
            
            # 1. Calcular tamanho necessário para o texto
            size_max, baseline_max = cv2.getTextSize(txt_max, font, f_scale, thickness)
            size_min, baseline_min = cv2.getTextSize(txt_min, font, f_scale, thickness)
            
            # Largura da legenda: margem esq + barra + gap + texto + margem dir
            max_text_w = max(size_max[0], size_min[0])
            legend_w = left_offset + bar_w + h_margin + max_text_w + 20
            
            # 2. Canvas da legenda (Fundo Branco)
            legend = np.full((h, int(legend_w), 3), 255, dtype=np.uint8)
            
            # 3. Barra de cores
            bar_h = h - (2 * v_margin)
            if bar_h <= 0: bar_h = h
            
            bar_pixels = np.linspace(255, 0, bar_h).astype(np.uint8).reshape(-1, 1)
            bar_pixels = np.repeat(bar_pixels, bar_w, axis=1)
            bar_colored = cv2.applyColorMap(bar_pixels, colormap)
            
            y_start = (h - bar_h) // 2
            legend[y_start:y_start+bar_h, left_offset:left_offset+bar_w] = bar_colored
            cv2.rectangle(legend, (left_offset, y_start), (left_offset+bar_w, y_start+bar_h), (180, 180, 180), 1)
            
            # 4. Desenhar Rótulos
            # Topo: Baseado em y_start + tamanho do texto para não cortar o topo
            text_x = left_offset + bar_w + h_margin
            cv2.putText(legend, txt_max, (text_x, y_start + size_max[1] // 2), 
                        font, f_scale, color, thickness, cv2.LINE_AA)
            
            # Base:
            cv2.putText(legend, txt_min, (text_x, y_start + bar_h), 
                        font, f_scale, color, thickness, cv2.LINE_AA)
            
            # Combinar com a imagem original
            combined = np.hstack((img, legend))
            return combined
        except Exception:
            return img
