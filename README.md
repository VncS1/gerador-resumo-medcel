# Assistente de Transcrição MedCel (AI)

Aplicacao desktop em Python para extrair audio de aulas em streaming (HLS/m3u8) e transcrever para texto utilizando a Inteligencia Artificial do modelo Whisper (via Groq API).

## Tecnologias Utilizadas

* Python 3.10+
* CustomTkinter
* yt-dlp
* Groq API (whisper-large-v3)
* FFmpeg

## Pre-requisitos de Desenvolvimento

1. Conta em console.groq.com e uma API Key gerada.
2. Executaveis do FFmpeg (ffmpeg.exe e ffprobe.exe) alocados na pasta ffmpeg_bin na raiz do projeto.
3. Arquivo .env na raiz do projeto com a variavel: GROQ_API_KEY=sua_chave_aqui

## Instalacao (Ambiente de Desenvolvimento Windows)

git clone https://github.com/VncS1/gerador-resumo-medcel
cd gerador-resumo-medcel

python -m venv venv

.\venv\Scripts\activate

pip install -r requirements.txt

## Execucao do Codigo-Fonte

python app_medcel.py

## Geracao da Build (.exe)

python -m PyInstaller --noconsole --onefile --icon=icone_medcel.ico --name="Assistente MedCel" app_medcel.py

## Estrutura de Distribuicao (Deploy)

Para distribuir o software final para um usuario, crie uma pasta contendo exclusivamente:
1. O executavel gerado na pasta dist/
2. A pasta ffmpeg_bin/
3. O arquivo .env com a chave ativa.
