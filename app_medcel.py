import os
import threading
import customtkinter as ctk
import time
from customtkinter import filedialog
import yt_dlp
from groq import Groq
from dotenv import load_dotenv
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

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

def formatar_e_resumir_texto(texto_bruto):
    cliente = Groq(api_key=CHAVE_API_GROQ)
    
    tamanho_chunk = 12000 
    chunks = [texto_bruto[i:i+tamanho_chunk] for i in range(0, len(texto_bruto), tamanho_chunk)]
    
    texto_formatado_acumulado = ""
    
    prompt_formatacao = """
    Você é um assistente acadêmico médico. Formate a seguinte parte de uma transcrição de aula.
    1. Mantenha TODO o conteúdo e detalhes técnicos originais.
    2. Organize em parágrafos coesos.
    3. NÃO use marcações Markdown (asteriscos, hashtags). Use letras maiúsculas para títulos.
    """
    
    for indice, chunk in enumerate(chunks):
        sucesso = False
        tentativas = 0
        
        while not sucesso and tentativas < 4:
            try:
                resposta = cliente.chat.completions.create(
                    messages=[
                        {"role": "system", "content": prompt_formatacao},
                        {"role": "user", "content": f"Parte {indice + 1}:\n\n{chunk}"}
                    ],
                    model="llama-3.1-8b-instant",
                    temperature=0.3
                )
                
                texto_formatado_acumulado += resposta.choices[0].message.content + "\n\n"
                sucesso = True
                time.sleep(2)
                
            except Exception as e:
                erro = str(e).lower()
                if "rate limit" in erro or "tokens per minute" in erro or "too large" in erro:
                    time.sleep(65)
                    tentativas += 1
                else:
                    raise e

    prompt_resumo = """
    Crie um resumo médico executivo contendo: principais diagnósticos, condutas e pontos-chave do texto fornecido.
    NÃO use marcações Markdown (asteriscos, hashtags).
    """
    
    try:
        resposta_resumo = cliente.chat.completions.create(
            messages=[
                {"role": "system", "content": prompt_resumo},
                {"role": "user", "content": texto_formatado_acumulado[-15000:]}
            ],
            model="llama-3.1-8b-instant",
            temperature=0.3
        )
        
        texto_formatado_acumulado += "\nRESUMO DA AULA\n\n" + resposta_resumo.choices[0].message.content
    except Exception:
        pass
        
    return texto_formatado_acumulado

def gerar_pdf(texto, caminho_saida):
    documento = SimpleDocTemplate(caminho_saida, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    estilos = getSampleStyleSheet()
    estilo_corpo = estilos["BodyText"]
    estilo_corpo.fontSize = 11
    estilo_corpo.leading = 15
    
    elementos = []
    
    paragrafos = texto.split('\n')
    for paragrafo in paragrafos:
        if paragrafo.strip():
            texto_limpo = paragrafo.replace('<', '&lt;').replace('>', '&gt;')
            elementos.append(Paragraph(texto_limpo, estilo_corpo))
            elementos.append(Spacer(1, 12))
            
    documento.build(elementos)

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
        
        self.botao_iniciar = ctk.CTkButton(self, text="Extrair, Formatar e Gerar PDF", command=self.iniciar_processamento)
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
            self.label_status.configure(text="Status: Baixando áudio da plataforma (1/4)...")
            caminho_mp3 = baixar_audio_do_link(url)
            
            self.label_status.configure(text="Status: Transcrevendo com Inteligência Artificial (2/4)...")
            texto_cru = transcrever_audio_nuvem(caminho_mp3)
            
            self.label_status.configure(text="Status: Estruturando e criando resumo (3/4)...")
            texto_formatado = formatar_e_resumir_texto(texto_cru)
            
            self.label_status.configure(text="Status: Gerando documento PDF (4/4)...")
            nome_arquivo = nome.replace(" ", "_") if nome else "transcricao_formatada"
            caminho_final = os.path.join(diretorio, f"{nome_arquivo}.pdf")
            
            gerar_pdf(texto_formatado, caminho_final)
                
            if os.path.exists(caminho_mp3):
                os.remove(caminho_mp3)
                
            self.caixa_texto.delete("0.0", "end")
            self.caixa_texto.insert("0.0", texto_formatado)
            
            self.label_status.configure(text=f"Sucesso! PDF salvo em: {caminho_final}", text_color="#2ECC71")
            
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