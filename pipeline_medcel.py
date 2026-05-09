import os
import threading
import customtkinter as ctk
from customtkinter import filedialog
import yt_dlp
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
CHAVE_API_GROQ = os.getenv("GROQ_API_KEY")

def baixar_audio_do_link(url_video):
    opcoes_download = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '32', 
        }],
        'outtmpl': 'audio_temporario.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'ffmpeg_location': './ffmpeg_bin'
    }
    
    with yt_dlp.YoutubeDL(opcoes_download) as extrator:
        extrator.download([url_video])
        
    return "audio_temporario.mp3"

def transcrever_audio_nuvem(caminho_audio):
    cliente = Groq(api_key=CHAVE_API_GROQ)
    
    with open(caminho_audio, "rb") as arquivo_mp3:
        transcricao = cliente.audio.transcriptions.create(
            file=(caminho_audio, arquivo_mp3.read()),
            model="whisper-large-v3",
            language="pt",
            prompt="A aula a seguir contém termos técnicos de medicina, anatomia, fisiopatologia, farmacologia e diagnósticos para residência médica."
        )
        
    return transcricao.text.strip()

class AplicativoMedCel(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Assistente de Transcrição Médica")
        self.geometry("600x600")
        
        self.diretorio_salvamento = os.getcwd()
        
        self.label_titulo = ctk.CTkLabel(self, text="Transcritor de Aulas", font=("Arial", 20, "bold"))
        self.label_titulo.pack(pady=(20, 10))
        
        self.input_url = ctk.CTkEntry(self, placeholder_text="Cole o link .m3u8 aqui", width=450)
        self.input_url.pack(pady=10)
        
        self.input_nome = ctk.CTkEntry(self, placeholder_text="Nome do arquivo (ex: aula_pediatria)", width=450)
        self.input_nome.pack(pady=10)
        
        self.frame_dir = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_dir.pack(pady=10)
        
        self.input_dir = ctk.CTkEntry(self.frame_dir, width=330)
        self.input_dir.insert(0, self.diretorio_salvamento)
        self.input_dir.configure(state="disabled")
        self.input_dir.pack(side="left", padx=(0, 10))
        
        self.botao_dir = ctk.CTkButton(self.frame_dir, text="Escolher Pasta", width=110, command=self.escolher_diretorio)
        self.botao_dir.pack(side="right")
        
        self.botao_iniciar = ctk.CTkButton(self, text="Extrair e Transcrever", command=self.iniciar_processamento)
        self.botao_iniciar.pack(pady=20)
        
        self.label_status = ctk.CTkLabel(self, text="", text_color="gray")
        self.label_status.pack(pady=5)
        
        self.caixa_texto = ctk.CTkTextbox(self, width=500, height=200)
        self.caixa_texto.pack(pady=10)
        
    def escolher_diretorio(self):
        dir_selecionado = filedialog.askdirectory(title="Selecione a pasta para salvar o resumo")
        if dir_selecionado:
            self.diretorio_salvamento = dir_selecionado
            self.input_dir.configure(state="normal")
            self.input_dir.delete(0, "end")
            self.input_dir.insert(0, self.diretorio_salvamento)
            self.input_dir.configure(state="disabled")
            
    def iniciar_processamento(self):
        url = self.input_url.get().strip()
        nome = self.input_nome.get().strip()
        
        if not url:
            self.label_status.configure(text="Erro: Insira o link da aula.", text_color="red")
            return
            
        if not CHAVE_API_GROQ:
            self.label_status.configure(text="Erro: Chave da Groq ausente no arquivo .env", text_color="red")
            return
            
        self.botao_iniciar.configure(state="disabled")
        self.botao_dir.configure(state="disabled")
        self.label_status.configure(text="Iniciando...", text_color="#F39C12")
        
        thread = threading.Thread(target=self.executar_pipeline, args=(url, nome, self.diretorio_salvamento))
        thread.start()
        
    def executar_pipeline(self, url, nome, diretorio):
        try:
            self.label_status.configure(text="Status: Baixando áudio da plataforma (1/3)...")
            caminho_mp3 = baixar_audio_do_link(url)
            
            self.label_status.configure(text="Status: Transcrevendo com Inteligência Artificial (2/3)...")
            texto_transcrito = transcrever_audio_nuvem(caminho_mp3)
            
            self.label_status.configure(text="Status: Salvando arquivo no computador (3/3)...")
            nome_arquivo = nome.replace(" ", "_") if nome else "transcricao"
            
            caminho_final = os.path.join(diretorio, f"{nome_arquivo}.txt")
            
            with open(caminho_final, "w", encoding="utf-8") as arquivo:
                arquivo.write(texto_transcrito)
                
            if os.path.exists(caminho_mp3):
                os.remove(caminho_mp3)
                
            self.caixa_texto.delete("0.0", "end")
            self.caixa_texto.insert("0.0", texto_transcrito)
            
            self.label_status.configure(text=f"Sucesso! Salvo em: {caminho_final}", text_color="#2ECC71")
            
        except Exception as e:
            self.label_status.configure(text=f"Erro no processamento: {str(e)}", text_color="red")
            if os.path.exists("audio_temporario.mp3"):
                os.remove("audio_temporario.mp3")
        finally:
            self.botao_iniciar.configure(state="normal")
            self.botao_dir.configure(state="normal")

if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    app = AplicativoMedCel()
    app.mainloop()