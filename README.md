# VerificacaoEdicao - Análise Forense de Multimídia

**Versão:** 1.4.1 | **Data:** 2026-03-20  
**Desenvolvimento:** Gerência de Perícias em Áudio e Vídeo (GPAV) / POLITEC-MT

Ferramenta profissional e auditável para **Análise Forense de Multimídia (Vídeo, Imagem e Áudio)**, projetada para detectar indícios de edição, adulteração, deepfakes e recompressão em arquivos digitais.

Desenvolvido para peritos forenses, o sistema combina múltiplas técnicas de análise em um pipeline automatizado, gerando relatórios técnicos detalhados (PDF/LaTeX) e logs auditáveis (JSONL).

---

## 🚀 Funcionalidades Principais

O sistema executa uma bateria de testes multimodal em cada arquivo processado:

### 1. Análise de Vídeo e Container
- **Integridade:** Cálculo de Hash SHA-512 para garantia de cadeia de custódia.
- **Metadados:** Extração profunda de parâmetros do container e streams.
- **Estrutura ISO BMFF:** Mapeia a ordem dos átomos físicos (moov, mdat) para inferir origem (Fast-Start vs Capture).
- **Continuidade Temporal:** Detecta cortes visuais (SCDET) e inconsistências de timestamps (PTS/DTS gaps/backjumps).
- **Compressão (Double Compression):** Análise estatística de Benford (tamanho de quadros) e Periodicidade de GOP (Fourier).
- **Quantização:** Extração de Scaling Lists do H.264 para identificação de assinatura de encoder.

### 2. Análise de Imagem (Image Forensics)
- **ELA (Error Level Analysis):** Identifica diferentes níveis de compressão em uma mesma imagem, sugerindo manipulação local.
- **Consistência de Ruído:** Compara a variância de ruído entre diferentes áreas para detectar montagens (splicing).
- **Copy-Move:** Detecta clonagem de elementos dentro da mesma imagem usando SIFT.
- **JPEG Ghosts:** Busca por rastros de versões anteriores da imagem salvas com qualidades diferentes.
- **Resampling:** Identifica artefatos de interpolação e redimensionamento.

### 3. Análise de Áudio (Audio Forensics) [NOVO]
- **Metadados e Streams:** Extração de codecs, sample rates e tags de origem.
- **Análise Espectral:** Plotagem e análise de descontinuidades no espectrograma.
- **Descontinuidade de Fase:** Identifica cortes abruptos que não respeitam a continuidade da onda sonora.
- **Silêncio Anômalo:** Detecta inserções de silêncio digital absoluto (zeros) no meio do arquivo, comuns em edições de áudio.
- **Deepfake de Voz:** Algoritmos para detecção de síntese de voz por IA e clonagem vocal.

### 4. Inteligência Artificial e Deepfake
- **Anomalias Frequenciais (FFT):** Identifica artefatos "checkerboard" típicos de geradores GAN.
- **Análise de Textura (LBP):** Detecta suavização artificial excessiva (beautification) na pele.
- **Consistência Física (Jitter):** Monitora a estabilidade temporal dos scores visuais. Variações rápidas indicam falhas frame-a-frame de Deepfakes.

### 5. Identificação de Fonte (PRNU)
- **Fingerprinting de Sensor:** Extrai o ruído padrão do sensor (PRNU) para identificar a câmera de origem.
- **Comparação Cruzada:** Calcula Matriz de Similaridade (PCE Score) entre múltiplos arquivos (vídeos e imagens) para verificar origem comum.

---

## 🛠️ Requisitos e Instalação

### Sistema
- **SO:** Windows 10/11 (Recomendado), Linux ou macOS.
- **Python:** 3.10 ou superior.
- **FFmpeg:** Obrigatório no PATH do sistema.

### Instalação
1. Clone este repositório.
2. Crie e ative um ambiente virtual:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```
3. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```

---

## 💻 Como Utilizar

O sistema opera via Interface Gráfica (GUI) ou Linha de Comando (CLI).

### Interface Gráfica (GUI)
Modo recomendado para análises interativas e geração de laudos.
```bash
python -m app.gui
```
1. Selecione múltiplos arquivos (Vídeos, Imagens ou Áudios).
2. Configure os parâmetros sensíveis no menu **Configurações**.
3. Clique em **Iniciar Análise Forense**.

### Linha de Comando (CLI)
Recomendado para automação.
```bash
python -m app.cli [ARQUIVO] --case-name "NOME_DO_CASO"
```

---

## 📂 Estrutura de Saída

Os resultados são organizados na pasta `cases/`:
```
cases/
└── case_[NOME]/
    ├── audit/
    │   └── audit.jsonl       # Log imutável (hash chain)
    ├── results/              # JSONs detalhados por módulo
    │   ├── *_file_analysis.json
    │   ├── *_audio_analysis.json
    │   ├── *_deepfake_analysis.json
    │   ├── *_prnu.json
    │   └── batch_manifest.json
    └── report/
        ├── report.pdf        # Laudo Técnico Final
        └── report.tex        # Fonte LaTeX
```

---

## 🏗️ Geração de Executável (Windows)

Para criar os arquivos `.exe` e o instalador:
1. Certifique-se de ter o **Inno Setup 6** instalado (opcional para instalador).
2. Execute o script de build:
   ```bash
   build_executable.bat
   ```
Os arquivos serão gerados na pasta `dist/` e o instalador em `dist-setup/`.

---

## ⚖️ Aviso Legal
Esta ferramenta fornece indicadores técnicos forenses para auxiliar peritos. A interpretação final dos resultados deve ser feita por um profissional qualificado (Perito Oficial ou Assistente Técnico), considerando o contexto completo da investigação. Falsos positivos podem ocorrer dependendo da compressão original e características do sensor.

