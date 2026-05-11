import os
import sys
import time
import threading
import subprocess
import glob
import customtkinter as ctk
from customtkinter import filedialog
import yt_dlp
from groq import Groq
from dotenv import load_dotenv
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER

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

def estruturar_texto_ia(texto_bruto):
    cliente = Groq(api_key=CHAVE_API_GROQ)
    tamanho_chunk = 5000
    chunks = [texto_bruto[i:i+tamanho_chunk] for i in range(0, len(texto_bruto), tamanho_chunk)]
    acumulado = ""
    
    prompt = """
    Você é um revisor de textos médicos. Sua tarefa é pegar a transcrição bruta e apenas adicionar pontuação e parágrafos.
    REGRA DE OURO: NÃO altere nenhuma palavra, NÃO resuma e NÃO corrija termos técnicos. Apenas pontue o texto para torná-lo legível.
    """
    
    for chunk in chunks:
        sucesso = False
        while not sucesso:
            try:
                res = cliente.chat.completions.create(
                    messages=[{"role": "system", "content": prompt}, {"role": "user", "content": chunk}],
                    model="llama-3.1-8b-instant",
                    temperature=0.1,
                    max_tokens=1500
                )
                acumulado += res.choices[0].message.content + "\n\n"
                sucesso = True
                time.sleep(2)
            except Exception as e:
                erro = str(e).lower()
                if "rate limit" in erro or "too large" in erro or "tokens" in erro:
                    time.sleep(62)
                else:
                    time.sleep(10)
    return acumulado

def gerar_resumo_ia(texto_bruto):
    cliente = Groq(api_key=CHAVE_API_GROQ)
    prompt = """
    Crie um resumo executivo médico baseado na transcrição fornecida. 
    O resumo deve conter: Principais Diagnósticos, Condutas sugeridas e Pontos de atenção para provas.
    Seja conciso e use tópicos. Não use Markdown.
    """
    texto_base = texto_bruto[-8000:] if len(texto_bruto) > 8000 else texto_bruto
    
    sucesso = False
    while not sucesso:
        try:
            res = cliente.chat.completions.create(
                messages=[{"role": "system", "content": prompt}, {"role": "user", "content": texto_base}],
                model="llama-3.1-8b-instant",
                temperature=0.3,
                max_tokens=1000
            )
            return res.choices[0].message.content
        except Exception as e:
            erro = str(e).lower()
            if "rate limit" in erro or "too large" in erro or "tokens" in erro:
                time.sleep(62)
            else:
                return "Erro ao gerar resumo devido a limitações de infraestrutura."

def gerar_pdf_completo(texto_raw, texto_clean, resumo, caminho_saida):
    doc = SimpleDocTemplate(caminho_saida, pagesize=A4)
    estilos = getSampleStyleSheet()
    
    estilo_titulo = ParagraphStyle('Titulo', parent=estilos['Heading1'], fontSize=16, alignment=TA_CENTER, spaceAfter=20)
    estilo_secao = ParagraphStyle('Secao', parent=estilos['Heading2'], fontSize=13, spaceBefore=15, spaceAfter=10, color="#2E5984")
    estilo_corpo = ParagraphStyle('Corpo', parent=estilos['BodyText'], fontSize=10, leading=14)
    
    elementos = []
    
    elementos.append(Paragraph("RELATÓRIO DE AULA - MEDCEL", estilo_titulo))
    
    elementos.append(Paragraph("1. RESUMO EXECUTIVO (IA)", estilo_secao))
    for p in resumo.split('\n'):
        if p.strip(): elementos.append(Paragraph(p.replace('<','&lt;').replace('>','&gt;'), estilo_corpo))
    
    elementos.append(PageBreak())
    elementos.append(Paragraph("2. TRANSCRIÇÃO ESTRUTURADA (IA)", estilo_secao))
    for p in texto_clean.split('\n'):
        if p.strip(): elementos.append(Paragraph(p.replace('<','&lt;').replace('>','&gt;'), estilo_corpo))
        
    elementos.append(PageBreak())
    elementos.append(Paragraph("3. TRANSCRIÇÃO ORIGINAL (BRUTA)", estilo_secao))
    for p in texto_raw.split('\n'):
        if p.strip(): elementos.append(Paragraph(p.replace('<','&lt;').replace('>','&gt;'), estilo_corpo))
        
    doc.build(elementos)

class AplicativoMedCel(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Assistente de Transcrição Médica")
        self.geometry("600x650")
        self.diretorio_salvamento = DIRETORIO_BASE
        
        ctk.CTkLabel(self, text="Transcritor de Aulas", font=("Arial", 20, "bold")).pack(pady=20)
        self.input_url = ctk.CTkEntry(self, placeholder_text="Link .m3u8", width=450); self.input_url.pack(pady=10)
        self.input_nome = ctk.CTkEntry(self, placeholder_text="Nome da aula", width=450); self.input_nome.pack(pady=10)
        
        self.frame_dir = ctk.CTkFrame(self, fg_color="transparent"); self.frame_dir.pack(pady=10)
        self.input_dir = ctk.CTkEntry(self.frame_dir, width=330); self.input_dir.insert(0, self.diretorio_salvamento)
        self.input_dir.configure(state="disabled"); self.input_dir.pack(side="left", padx=5)
        ctk.CTkButton(self.frame_dir, text="Pasta", width=100, command=self.escolher_diretorio).pack(side="right")
        
        self.botao_iniciar = ctk.CTkButton(self, text="Gerar Relatório Completo", command=self.iniciar_processamento)
        self.botao_iniciar.pack(pady=20)
        self.label_status = ctk.CTkLabel(self, text="", text_color="gray"); self.label_status.pack()
        self.caixa_texto = ctk.CTkTextbox(self, width=500, height=200); self.caixa_texto.pack(pady=10)
        
    def escolher_diretorio(self):
        d = filedialog.askdirectory()
        if d: 
            self.diretorio_salvamento = d
            self.input_dir.configure(state="normal"); self.input_dir.delete(0, 'end'); self.input_dir.insert(0, d); self.input_dir.configure(state="disabled")
            
    def iniciar_processamento(self):
        u, n = self.input_url.get().strip(), self.input_nome.get().strip()
        if u and CHAVE_API_GROQ:
            self.botao_iniciar.configure(state="disabled")
            threading.Thread(target=self.executar_pipeline, args=(u, n, self.diretorio_salvamento)).start()
            
    def executar_pipeline(self, url, nome, diretorio):
        try:
            self.label_status.configure(text="Baixando áudio...")
            mp3 = baixar_audio_do_link(url)
            
            self.label_status.configure(text="Transcrevendo (Bruto)...")
            raw = transcrever_audio_nuvem(mp3)
            
            self.label_status.configure(text="Estruturando texto...")
            clean = estruturar_texto_ia(raw)
            
            self.label_status.configure(text="Gerando resumo...")
            resumo = gerar_resumo_ia(raw)
            
            self.label_status.configure(text="Gerando PDF...")
            arq = f"{nome.replace(' ','_') if nome else 'aula'}.pdf"
            caminho = os.path.join(diretorio, arq)
            gerar_pdf_completo(raw, clean, resumo, caminho)
            
            if os.path.exists(mp3): os.remove(mp3)
            self.caixa_texto.delete("0.0", "end"); self.caixa_texto.insert("0.0", resumo)
            self.label_status.configure(text=f"Sucesso: {arq}", text_color="#2ECC71")
        except Exception as e:
            erro_str = str(e).lower()
            if "seconds of audio per hour" in erro_str:
                self.label_status.configure(text="Limite de transcrição atingido. Aguarde 15min.", text_color="red")
            else:
                self.label_status.configure(text=f"Erro: {str(e)}", text_color="red")
        finally:
            for lixo in glob.glob(os.path.join(DIRETORIO_BASE, 'audio_temporario.*')):
                try: os.remove(lixo)
                except: pass
            self.botao_iniciar.configure(state="normal")

if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    AplicativoMedCel().mainloop()