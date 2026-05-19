import os
import sys
import time
import threading
import subprocess
import glob
import re
import html
import customtkinter as ctk
from customtkinter import filedialog
import yt_dlp
from groq import Groq
from google import genai
from google.genai import types
from dotenv import load_dotenv
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib import colors

def obter_diretorio_base():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.abspath(os.path.dirname(__file__))

DIRETORIO_BASE = obter_diretorio_base()
CAMINHO_FFMPEG = os.path.join(DIRETORIO_BASE, 'ffmpeg_bin')
CAMINHO_FFMPEG_EXE = os.path.join(CAMINHO_FFMPEG, 'ffmpeg.exe')

os.environ["PATH"] = CAMINHO_FFMPEG + os.pathsep + os.environ.get("PATH", "")

load_dotenv(os.path.join(DIRETORIO_BASE, '.env'))
CHAVE_API_GROQ = os.getenv("GROQ_API_KEY")
CHAVE_API_GEMINI = os.getenv("GEMINI_API_KEY")

def baixar_audio_do_link(url_video):
    caminho_base = os.path.join(DIRETORIO_BASE, 'audio_temporario')
    caminho_download = f"{caminho_base}.%(ext)s"
    caminho_mp3 = f"{caminho_base}.mp3"
    
    opcoes_download = {
        'format': 'bestaudio/best',
        'outtmpl': caminho_download,
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'ffmpeg_location': CAMINHO_FFMPEG
    }
    
    with yt_dlp.YoutubeDL(opcoes_download) as extrator:
        extrator.download([url_video])
        
    arquivos = glob.glob(f"{caminho_base}.*")
    arquivo_baixado = None
    for arq in arquivos:
        if not arq.endswith('.temp') and not arq.endswith('.mp3'):
            arquivo_baixado = arq
            break
            
    if not arquivo_baixado:
        raise Exception("Arquivo de mídia não encontrado.")
        
    comando = [
        CAMINHO_FFMPEG_EXE, '-y', '-i', arquivo_baixado,
        '-vn', '-ar', '16000', '-ac', '1', '-b:a', '32k', caminho_mp3
    ]
    
    subprocess.run(comando, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    if os.path.exists(arquivo_baixado):
        try: os.remove(arquivo_baixado)
        except: pass
            
    return caminho_mp3

def transcrever_audio_nuvem(caminho_audio):
    cliente = Groq(api_key=CHAVE_API_GROQ)
    with open(caminho_audio, "rb") as arquivo_mp3:
        transcricao = cliente.audio.transcriptions.create(
            file=(caminho_audio, arquivo_mp3.read()),
            model="whisper-large-v3-turbo",
            language="pt",
            prompt="Aula médica com termos técnicos, diagnósticos e condutas."
        )
    return transcricao.text.strip()

def _criar_cliente_gemini():
    return genai.Client(api_key=CHAVE_API_GEMINI, http_options={'timeout': 600})

def _executar_chamada_gemini(cliente, prompt, texto_bruto):
    configuracoes = types.GenerateContentConfig(
        candidate_count=1,
        temperature=0.2,
        max_output_tokens=65535
    )
    
    tentativas = 0
    ultimo_erro = ""
    tempos_espera = [10, 20, 40]
    
    while tentativas < 3:
        try:
            resposta = cliente.models.generate_content(
                model='gemini-2.5-flash',
                contents=[prompt, texto_bruto],
                config=configuracoes
            )
            return resposta.text
        except Exception as e:
            ultimo_erro = str(e)
            if tentativas < 2:
                time.sleep(tempos_espera[tentativas])
            tentativas += 1
            
    return f"Falha_Crítica: {ultimo_erro}"

def gerar_material_estudo_avancado(cliente_gemini, texto_bruto):
    caminho_provas = os.path.join(DIRETORIO_BASE, 'provas.txt')
    exemplos_provas = ""
    
    if os.path.exists(caminho_provas):
        try:
            with open(caminho_provas, 'r', encoding='utf-8') as f:
                exemplos_provas = f.read()
        except Exception:
            pass

    prompt = f"""
    Atue como um Examinador Chefe das bancas de residência médica da USP SP, USP Ribeirão Preto, SUS SP e Enamed.
    Seu objetivo é ler a transcrição bruta desta aula e criar o material de estudo mais exaustivo e completo possível.
    
    ESTRUTURA OBRIGATÓRIA:
    
    # RESUMO TEÓRICO APROFUNDADO (EXTREMAMENTE DETALHADO)
    Não omita absolutamente nenhuma informação dita pelo professor. Explique a fisiopatologia, quadro clínico, diagnóstico e tratamento de forma extensa, densa e com altíssima riqueza de detalhes. 
    Utilize tabelas em Markdown (com |) para esquematizar diagnósticos diferenciais, classificações ou esquemas terapêuticos.
    Destaque as "pegadinhas" clássicas, exceções clínicas e o foco de cobrança das bancas USP, SUS SP e Enamed.
    
    # CADERNO DE QUESTÕES (15 CASOS CLÍNICOS)
    Forneça exatamente 15 questões de múltipla escolha (A, B, C, D).
    As questões DEVEM ser formulações de casos clínicos complexos, espelhando fielmente a dificuldade, o estilo e resgatando a estrutura de questões reais destas instituições.
    NÃO coloque o gabarito ou dicas nesta seção. Apenas os enunciados longos e as alternativas.
    
    # GABARITO COMENTADO
    Indique a alternativa correta de cada uma das 15 questões e explique minuciosamente o raciocínio clínico, justificando o erro estrutural de cada uma das outras alternativas.
    
    REFERÊNCIA DE ESTILO E DIFICULDADE (Siga estritamente o padrão abaixo para formular as questões):
    {exemplos_provas}
    """
    return _executar_chamada_gemini(cliente_gemini, prompt, texto_bruto)

def _formatar_texto_celula(texto):
    texto_escapado = html.escape(texto)
    return re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', texto_escapado)

def _renderizar_tabela(table_data, estilo_corpo):
    max_cols = max(len(r) for r in table_data)
    for r in table_data:
        while len(r) < max_cols:
            r.append(Paragraph("", estilo_corpo))
    t = Table(table_data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#2B6CB0")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#A0AEC0")),
        ('BOTTOMPADDING', (0,0), (-1,0), 8),
        ('TOPPADDING', (0,0), (-1,0), 8),
    ]))
    return t

def compilar_pdf_estudo(markdown_text, caminho_saida):
    doc = SimpleDocTemplate(caminho_saida, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    estilos = getSampleStyleSheet()
    
    estilo_titulo_doc = ParagraphStyle('TituloDoc', parent=estilos['Heading1'], fontSize=18, alignment=TA_CENTER, spaceAfter=25, textColor=colors.HexColor("#1A365D"))
    estilo_h1 = ParagraphStyle('H1', parent=estilos['Heading2'], fontSize=15, spaceBefore=22, spaceAfter=12, textColor=colors.HexColor("#2B6CB0"))
    estilo_h2 = ParagraphStyle('H2', parent=estilos['Heading3'], fontSize=13, spaceBefore=14, spaceAfter=8, textColor=colors.HexColor("#2D3748"))
    estilo_corpo = ParagraphStyle('Corpo', parent=estilos['BodyText'], fontSize=11, leading=16, textColor=colors.black)
    
    elementos = []
    elementos.append(Paragraph("MATERIAL DIRECIONADO PARA RESIDÊNCIA", estilo_titulo_doc))
    
    in_table = False
    table_data = []
    
    linhas = markdown_text.split('\n')
    for linha in linhas:
        linha_limpa = linha.strip()
        
        if not linha_limpa:
            if in_table and table_data:
                elementos.append(_renderizar_tabela(table_data, estilo_corpo))
                elementos.append(Spacer(1, 15))
                table_data = []
            in_table = False
            elementos.append(Spacer(1, 6))
            continue
            
        if linha_limpa.startswith('|') and linha_limpa.endswith('|'):
            in_table = True
            if '---' in linha_limpa:
                continue
            celulas = [c.strip() for c in linha_limpa.split('|')[1:-1]]
            linha_formatada = [Paragraph(_formatar_texto_celula(c), estilo_corpo) for c in celulas]
            table_data.append(linha_formatada)
            continue
            
        if in_table and table_data:
            elementos.append(_renderizar_tabela(table_data, estilo_corpo))
            elementos.append(Spacer(1, 15))
            table_data = []
            in_table = False
            
        if "GABARITO COMENTADO" in linha_limpa.upper():
            elementos.append(PageBreak())
            
        texto_formatado = _formatar_texto_celula(linha_limpa)
        
        if linha_limpa.startswith('### '):
            elementos.append(Paragraph(texto_formatado[4:], estilo_h2))
        elif linha_limpa.startswith('## '):
            elementos.append(Paragraph(texto_formatado[3:], estilo_h1))
        elif linha_limpa.startswith('# '):
            elementos.append(Paragraph(texto_formatado[2:], estilo_h1))
        elif linha_limpa.startswith('- ') or linha_limpa.startswith('* '):
            elementos.append(Paragraph("• " + texto_formatado[2:], estilo_corpo))
        else:
            elementos.append(Paragraph(texto_formatado, estilo_corpo))
            
    if in_table and table_data:
        elementos.append(_renderizar_tabela(table_data, estilo_corpo))
        
    doc.build(elementos)

class AplicativoMedCel(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Assistente de Transcrição Médica")
        self.geometry("600x700")
        self.diretorio_salvamento = DIRETORIO_BASE
        
        self.cliente_gemini = None
        if CHAVE_API_GEMINI:
            self.cliente_gemini = _criar_cliente_gemini()
        
        ctk.CTkLabel(self, text="Transcritor de Aulas", font=("Arial", 20, "bold")).pack(pady=20)
        self.input_url = ctk.CTkEntry(self, placeholder_text="Link .m3u8", width=450)
        self.input_url.pack(pady=10)
        self.input_nome = ctk.CTkEntry(self, placeholder_text="Nome da aula", width=450)
        self.input_nome.pack(pady=10)
        
        self.frame_dir = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_dir.pack(pady=10)
        self.input_dir = ctk.CTkEntry(self.frame_dir, width=330)
        self.input_dir.insert(0, self.diretorio_salvamento)
        self.input_dir.configure(state="disabled")
        self.input_dir.pack(side="left", padx=5)
        ctk.CTkButton(self.frame_dir, text="Pasta", width=100, command=self.escolher_diretorio).pack(side="right")
        
        self.botao_iniciar = ctk.CTkButton(self, text="Gerar Material e Questões", command=self.iniciar_processamento)
        self.botao_iniciar.pack(pady=15)
        
        self.barra_progresso = ctk.CTkProgressBar(self, width=400, mode="indeterminate")
        self.barra_progresso.pack(pady=5)
        self.barra_progresso.set(0)
        
        self.label_status = ctk.CTkLabel(self, text="", text_color="gray")
        self.label_status.pack(pady=5)
        
        self.caixa_texto = ctk.CTkTextbox(self, width=500, height=200)
        self.caixa_texto.pack(pady=10)
        
    def escolher_diretorio(self):
        d = filedialog.askdirectory()
        if d: 
            self.diretorio_salvamento = d
            self.input_dir.configure(state="normal")
            self.input_dir.delete(0, 'end')
            self.input_dir.insert(0, d)
            self.input_dir.configure(state="disabled")
            
    def iniciar_processamento(self):
        u, n = self.input_url.get().strip(), self.input_nome.get().strip()
        if not u:
            self.label_status.configure(text="Erro: Link vazio.", text_color="red")
            return
        if not CHAVE_API_GEMINI or not CHAVE_API_GROQ:
            self.label_status.configure(text="Erro: Chaves API ausentes no .env", text_color="red")
            return
            
        if self.cliente_gemini is None:
            self.cliente_gemini = _criar_cliente_gemini()
            
        self.botao_iniciar.configure(state="disabled")
        self.barra_progresso.start()
        
        threading.Thread(target=self.executar_pipeline, args=(u, n, self.diretorio_salvamento)).start()
        
    def executar_pipeline(self, url, nome, diretorio):
        try:
            self.label_status.configure(text="Baixando áudio...")
            mp3 = baixar_audio_do_link(url)
            
            self.label_status.configure(text="Transcrevendo via Groq (Rápido)...")
            raw = transcrever_audio_nuvem(mp3)
            
            self.label_status.configure(text="Gemini 2.5 Flash: Analisando referências e gerando material...")
            material_final = gerar_material_estudo_avancado(self.cliente_gemini, raw)
            
            if material_final.startswith("Falha_Crítica:"):
                raise Exception(material_final)
            
            self.label_status.configure(text="Compilando PDF Final...")
            arq = f"{nome.replace(' ','_') if nome else 'aula'}.pdf"
            caminho = os.path.join(diretorio, arq)
            compilar_pdf_estudo(material_final, caminho)
            
            if os.path.exists(mp3): os.remove(mp3)
            self.caixa_texto.delete("0.0", "end")
            self.caixa_texto.insert("0.0", material_final)
            self.label_status.configure(text=f"Sucesso: {arq}", text_color="#2ECC71")
        except Exception as e:
            self.label_status.configure(text=f"Erro de Execução. Veja o log abaixo.", text_color="red")
            self.caixa_texto.delete("0.0", "end")
            self.caixa_texto.insert("0.0", str(e))
        finally:
            self.barra_progresso.stop()
            self.barra_progresso.set(0)
            for lixo in glob.glob(os.path.join(DIRETORIO_BASE, 'audio_temporario.*')):
                try: os.remove(lixo)
                except: pass
            self.botao_iniciar.configure(state="normal")

if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    AplicativoMedCel().mainloop()