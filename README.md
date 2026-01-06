# Forensic Video Analyzer

Ferramenta profissional e auditável para **Análise Forense de Multimídia (Vídeo e Imagem)**, projetada para detectar indícios de edição, adulteração, deepfakes e recompressão em arquivos digitais.

Desenvolvido para peritos forenses, o sistema combina múltiplas técnicas de análise em um pipeline automatizado, gerando relatórios técnicos detalhados (PDF) e logs auditáveis (JSONL).

---

## 🚀 Funcionalidades Principais

O sistema executa uma bateria de testes em cada arquivo processado:

### 1. Análise de Arquivo e Container
- **Integridade:** Cálculo de Hash SHA-512 para garantia de cadeia de custódia.
- **Metadados:** Extração profunda de metadados do container e streams.
- **Assinaturas de Edição:** Detecção automática de traços de softwares (Adobe Premiere, HandBrake, FFmpeg, etc.) nos metadados.

### 2. Estrutura Física (Atom Map)
- **Análise ISO BMFF:** Mapeia a ordem dos átomos físicos (moov, mdat) para inferir a origem.
- **Detecção de Fast-Start:** Identifica arquivos otimizados para web (típico de redes sociais/editores) vs. arquivos de captura direta (mdat antes do moov).

### 3. Análise Temporal e Continuidade
- **Cortes Visuais:** Detecção de mudanças bruscas de cena (SCDET) que podem indicar cortes de edição.
- **Linearidade PTS/DTS:** Verifica inconsistências nos timestamps de apresentação e decodificação (gaps, backjumps) causados por manipulação ou remuxing.

### 4. Análise de Compressão (Double Compression)
- **Estatística de Benford:** Verifica se a distribuição dos tamanhos dos quadros (I/P/B) obedece à Lei de Benford. Desvios indicam reprocessamento.
- **Análise de Fourier (GOP):** Detecta periodicidade rígida na estrutura de compressão, comum em vídeos reencodados.

### 5. Análise de Quantização
- **Matrizes de Quantização:** Extrai Scaling Lists do H.264 para identificar se são customizadas (assinatura de encoder).
- **Estimativa de Qualidade:** Calcula Bits-Per-Pixel (BPP) para inferir nível de recompressão.

### 6. Identificação de Fonte (PRNU)
- **Fingerprinting de Sensor:** Extrai o ruído padrão do sensor (PRNU) para identificar a câmera de origem.
- **Comparação Cruzada:** Calcula Matriz de Similaridade (PCE Score) entre múltiplos vídeos para verificar se vieram do mesmo dispositivo.

### 7. Detecção de Deepfake e Consistência Física
- **Detecção de Anomalias Frequenciais (FFT):** Identifica artefatos "checkerboard" típicos de geradores GAN (Generative Adversarial Networks).
- **Análise de Textura (LBP):** Detecta suavização artificial excessiva (beautification/faceswap) na pele.
- **Consistência Física (Flickering & Noise):**
    - **Imagens:** Compara a variância de ruído entre o sujeito (Face/Corpo) e o fundo para detectar montagens (splicing).
    - **Vídeos:** Monitora a estabilidade temporal (Jitter) dos scores visuais. Variações rápidas indicam falha na renderização frame-a-frame do Deepfake.

---

## 🛠️ Requisitos de Instalação

### Sistema
- **Sistema Operacional:** Windows 10/11, Linux ou macOS.
- **Python:** Versão 3.10 ou superior.
- **FFmpeg:** Obrigatório. O executável deve estar acessível no PATH do sistema.

### Instalação das Dependências

1. Clone ou baixe este repositório.
2. Navegue até a pasta do projeto.
3. Instale as bibliotecas Python necessárias:

```bash
pip install -r requirements.txt
```

*Nota: Em alguns sistemas Windows, pode ser necessário instalar o pacote `tzdata` separadamente se houver erros de fuso horário.*

---

## 💻 Como Utilizar

O sistema pode ser operado via Interface Gráfica (GUI) para facilidade de uso ou Linha de Comando (CLI) para automação e scripts.

### Interface Gráfica (GUI)

Modo recomendado para análises interativas.

1. Execute o comando:
   ```bash
   python -m app.gui
   ```
2. Clique em **"Selecionar Vídeo(s)"** e escolha um ou mais arquivos.
3. Clique em **"Iniciar Análise Forense"**.
4. Escolha a pasta onde os resultados e o relatório serão salvos.
5. Acompanhe o progresso na janela de logs.

**Configurações Avançadas:**
O menu "Configurações" permite ajustar parâmetros sensíveis, como:
- **Deepfake:** Limiar de ruído, Sensibilidade de Jitter e Modo Rápido.
- **Imagem:** Sensibilidade do algoritmo de Copy-Move e qualidade ELA.
- **Vídeo:** Limite de quadros para extração de PRNU.

### Linha de Comando (CLI)

Modo recomendado para processamento em lote ou servidores.

**Sintaxe Básica:**
```bash
python -m app.cli [ARQUIVO_DE_VIDEO] [OPCOES]
```

**Exemplo:**
```bash
python -m app.cli "C:\Videos\suspeito.mp4" --case-name "Caso_001"
```

**Opções Disponíveis:**
- `--case-name [NOME]`: Define o nome da pasta do caso. (Padrão: automático baseado no arquivo).
- `--threshold [0.0-1.0]`: Ajusta a sensibilidade da detecção de cortes (Padrão: 0.3).
- `--deepfake-noise [10-90]`: Define o limiar de sensibilidade a ruído para detecção de splicing (Padrão: 50).
- `--deepfake-jitter [5-50]`: Define a sensibilidade para instabilidade temporal em vídeos (Padrão: 15).
- `--deepfake-fast`: Ativa o modo rápido (pula análises pesadas de FFT/LBP frames-a-frame).
- `--help`: Exibe todas as opções disponíveis.

---

## 📂 Saída e Relatórios

Para cada análise, o sistema cria uma estrutura de diretórios organizada dentro da pasta `cases/`:

```
cases/
└── case_[NOME_DO_CASO]/
    ├── audit/
    │   └── audit.jsonl       # Log forense imutável com hash chain de todos os eventos.
    ├── results/
    │   ├── batch_manifest.json # Índice dos arquivos analisados.
    │   ├── *_file_analysis.json
    │   ├── *_continuity.json
    │   ├── *_compression.json
    │   ├── *_quantization.json
    │   ├── *_prnu.json
    │   ├── *_prnu.json
    │   ├── *_deepfake_analysis.json # Resultados detectados de Face/Corpo e inconsistências.
    │   └── prnu_matrix.json    # Matriz de comparação (se houver múltiplos vídeos).
    └── report/
        ├── report.pdf          # Relatório Final em PDF (Laudo Técnico).
        └── report.tex          # Código fonte LaTeX (para arquivamento/edição).
```

### O Relatório (PDF)
O relatório gerado é um documento técnico completo contendo:
- Resumo do caso e timestamps.
- Tabelas detalhadas de metadados.
- Gráficos e tabelas de conformidade estatística (Benford).
- Diagnósticos automáticos (Indícios de Edição, Status de PRNU, Alertas de GOP).
- Tabelas de comparação de fonte (se aplicável).

---

## ⚖️ Aviso Legal
Esta ferramenta fornece indicadores técnicos forenses para auxiliar peritos. A interpretação final dos resultados deve ser feita por um profissional qualificado, considerando o contexto completo da investigação. Falsos positivos podem ocorrer dependendo da natureza da compressão original.
