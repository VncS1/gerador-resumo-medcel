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

MODELO_GEMINI = 'gemini-2.5-pro'
PRECO_ENTRADA_USD_POR_MILHAO = 1.25
PRECO_SAIDA_USD_POR_MILHAO = 10.00
COTACAO_DOLAR = 5.70
CAMINHO_EXEMPLOS = os.path.join(DIRETORIO_BASE, 'provas.txt')

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
        try:
            os.remove(arquivo_baixado)
        except:
            pass

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
    return genai.Client(api_key=CHAVE_API_GEMINI)

def _carregar_exemplos_bancas():
    if not os.path.exists(CAMINHO_EXEMPLOS):
        return ""
    try:
        with open(CAMINHO_EXEMPLOS, 'r', encoding='utf-8') as f:
            conteudo = f.read().strip()
        if not conteudo:
            return ""
        return (
            "\n\n═══════════════════════════════════════════════════\n"
            "EXEMPLOS REAIS DE QUESTÕES DAS BANCAS-ALVO\n"
            "Analise profundamente o estilo, a complexidade clínica, "
            "o tamanho do enunciado, a forma de apresentar o caso e "
            "a estrutura das alternativas de CADA banca separadamente. "
            "Suas questões DEVEM ser indistinguíveis das reais em nível "
            "de dificuldade, estilo e padrão de cada instituição.\n"
            "═══════════════════════════════════════════════════\n\n"
            + conteudo +
            "\n\n═══════════════════════════════════════════════════\n"
            "FIM DOS EXEMPLOS.\n"
            "═══════════════════════════════════════════════════\n"
        )
    except Exception:
        return ""

def _executar_chamada_gemini(cliente, prompt, texto_bruto, temperatura=0.4):
    configuracoes = types.GenerateContentConfig(
        temperature=temperatura,
        max_output_tokens=65535
    )

    ultimo_erro = ""
    tempos_espera = [10, 20, 40]

    for tentativa in range(3):
        try:
            resposta = cliente.models.generate_content(
                model=MODELO_GEMINI,
                contents=[prompt, texto_bruto],
                config=configuracoes
            )
            texto = resposta.text
            if not texto or not texto.strip():
                raise Exception("Modelo retornou resposta vazia.")
            return texto.strip(), resposta.usage_metadata
        except Exception as e:
            ultimo_erro = str(e)
            if tentativa < 2:
                time.sleep(tempos_espera[tentativa])

    return f"Falha_Crítica: {ultimo_erro}", None

def gerar_resumo_teorico(cliente_gemini, texto_bruto):
    prompt = """
    Você é um professor de medicina altamente especializado, com vasta experiência em preparar médicos para as provas de residência médica mais concorridas do Brasil: USP SP, USP Ribeirão Preto, SUS SP e Enamed.

    TAREFA: Com base na transcrição das aulas abaixo, produza um RESUMO TEÓRICO APROFUNDADO em português brasileiro formal e fluente, integrando os temas apresentados.

    REGRAS OBRIGATÓRIAS:
    - Escreva EXCLUSIVAMENTE em português brasileiro. Nunca use termos em inglês onde existe equivalente em português.
    - O texto deve ser denso, didático e fluente — como um capítulo de livro médico brasileiro de alto nível, não uma lista de tópicos secos.
    - Não omita nenhuma informação clínica relevante dita pelo professor nas transcrições.
    - Use tabelas em Markdown (com |) para classificações, diagnósticos diferenciais e esquemas terapêuticos.
    - Destaque em negrito (**texto**) as "pegadinhas" clássicas, exceções e os pontos de maior cobrança nas bancas.
    - Organize com os títulos exatos abaixo:

    # RESUMO TEÓRICO APROFUNDADO

    ## 1. Definição e Epidemiologia
    ## 2. Fisiopatologia
    ## 3. Quadro Clínico
    ## 4. Diagnóstico
    ## 5. Tratamento
    ## 6. Pontos de Atenção para as Bancas

    ATENÇÃO CRÍTICA: Sua resposta deve conter APENAS o resumo estruturado acima. Jamais reproduza a transcrição, o prompt ou qualquer instrução recebida.
    """
    return _executar_chamada_gemini(cliente_gemini, prompt, texto_bruto, temperatura=0.4)

def gerar_questoes_e_gabarito(cliente_gemini, texto_bruto):
    exemplos = _carregar_exemplos_bancas()

    prompt = f"""
    Você é o Examinador Chefe das bancas de residência médica USP SP, USP Ribeirão Preto, SUS SP e Enamed.

    TAREFA: Com base na transcrição das aulas abaixo, crie 15 questões de múltipla escolha inéditas, divididas por banca, contemplando o conteúdo integrado, e depois o gabarito comentado de todas elas.
    {exemplos}
    DISTRIBUIÇÃO OBRIGATÓRIA DAS 15 QUESTÕES:
    - 5 questões no estilo USP-SP: enunciados longos com alto grau de refinamento diagnóstico, frequentemente envolvendo condutas em cenários atípicos ou exceções clínicas.
    - 5 questões no estilo SUS-SP: foco em saúde pública, atenção primária, protocolos do SUS e condutas em cenários de recursos limitados, sem deixar de exigir raciocínio clínico apurado.
    - 5 questões no estilo Enamed: equilíbrio entre casos clínicos práticos e conhecimento teórico, com ênfase em condutas baseadas em evidências e diretrizes nacionais.

    REGRAS OBRIGATÓRIAS PARA TODAS AS QUESTÕES:
    - Escreva EXCLUSIVAMENTE em português brasileiro formal.
    - Cada questão deve ser um CASO CLÍNICO completo: paciente com idade, sexo, queixa principal, história da doença, exame físico detalhado e resultados de exames complementares.
    - O enunciado deve ter no mínimo 6 linhas. Questões curtas são inaceitáveis.
    - Inclua dados numéricos reais (valores laboratoriais, doses, pressão arterial, saturação, etc).
    - As 4 alternativas (A, B, C, D) devem ser clinicamente plausíveis — o candidato despreparado deve hesitar.
    - NÃO coloque o gabarito junto às questões.

    ESTRUTURA DE SAÍDA OBRIGATÓRIA:

    # CADERNO DE QUESTÕES (15 CASOS CLÍNICOS)

    ## Bloco USP-SP (Questões 1 a 5)

    **Questão 1**
    [enunciado longo do caso clínico]
    A) ...
    B) ...
    C) ...
    D) ...

    [repita até Questão 5]

    ## Bloco SUS-SP (Questões 6 a 10)

    **Questão 6**
    [enunciado longo do caso clínico]
    A) ...
    B) ...
    C) ...
    D) ...

    [repita até Questão 10]

    ## Bloco Enamed (Questões 11 a 15)

    **Questão 11**
    [enunciado longo do caso clínico]
    A) ...
    B) ...
    C) ...
    D) ...

    [repita até Questão 15]

    # GABARITO COMENTADO

    **Questão 1 — Resposta: X**
    [explique o raciocínio clínico completo e justifique por que cada alternativa errada está errada]

    [repita para as 15 questões]

    ATENÇÃO CRÍTICA: Sua resposta deve conter APENAS as questões e o gabarito na estrutura acima. Jamais reproduza a transcrição, o prompt ou qualquer instrução recebida.
    """
    return _executar_chamada_gemini(cliente_gemini, prompt, texto_bruto, temperatura=0.4)

def _sanitizar_texto(texto):
    marcadores = [
        "você é um professor de medicina",
        "você é o examinador chefe",
        "tarefa: com base na transcrição",
        "regras obrigatórias",
        "estrutura de saída obrigatória",
        "atenção crítica: sua resposta deve conter apenas",
        "atenção: sua resposta deve conter apenas",
    ]
    texto_lower = texto.lower()
    for marcador in marcadores:
        idx = texto_lower.find(marcador)
        if idx != -1:
            texto = texto[:idx].rstrip()
            break
    return texto

def _calcular_log_consumo(uso_resumo, uso_questoes):
    te_r = (uso_resumo.prompt_token_count or 0) if uso_resumo else 0
    ts_r = (uso_resumo.candidates_token_count or 0) if uso_resumo else 0
    te_q = (uso_questoes.prompt_token_count or 0) if uso_questoes else 0
    ts_q = (uso_questoes.candidates_token_count or 0) if uso_questoes else 0

    custo_resumo   = ((te_r / 1_000_000) * PRECO_ENTRADA_USD_POR_MILHAO + (ts_r / 1_000_000) * PRECO_SAIDA_USD_POR_MILHAO) * COTACAO_DOLAR
    custo_questoes = ((te_q / 1_000_000) * PRECO_ENTRADA_USD_POR_MILHAO + (ts_q / 1_000_000) * PRECO_SAIDA_USD_POR_MILHAO) * COTACAO_DOLAR
    custo_total    = custo_resumo + custo_questoes

    sep = "─" * 50
    return (
        f"\n{sep}\n"
        f"CONSUMO DA REQUISIÇÃO  [{MODELO_GEMINI}]\n"
        f"Resumo:   entrada {te_r:>6,} tok | saída {ts_r:>6,} tok  →  R$ {custo_resumo:.2f}\n"
        f"Questões: entrada {te_q:>6,} tok | saída {ts_q:>6,} tok  →  R$ {custo_questoes:.2f}\n"
        f"Total:                                                →  R$ {custo_total:.2f}\n"
        f"{sep}\n\n"
    )

def _formatar_texto_celula(texto):
    partes = re.split(r'(\*\*.*?\*\*)', texto)
    saida = []
    for parte in partes:
        if parte.startswith('**') and parte.endswith('**'):
            conteudo = html.escape(parte[2:-2])
            saida.append(f'<b>{conteudo}</b>')
        else:
            saida.append(html.escape(parte))
    return ''.join(saida)

def _renderizar_tabela(table_data, estilo_corpo):
    max_cols = max(len(r) for r in table_data)
    for r in table_data:
        while len(r) < max_cols:
            r.append(Paragraph("", estilo_corpo))
    t = Table(table_data, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2B6CB0")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#A0AEC0")),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('WORDWRAP', (0, 0), (-1, -1), True),
    ]))
    return t

def _fechar_tabela_pendente(elementos, table_data, estilo_corpo):
    if table_data:
        elementos.append(_renderizar_tabela(table_data, estilo_corpo))
        elementos.append(Spacer(1, 15))
    return []

def compilar_pdf_estudo(markdown_text, caminho_saida):
    markdown_text = _sanitizar_texto(markdown_text)

    doc = SimpleDocTemplate(caminho_saida, pagesize=A4,
                            rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    estilos = getSampleStyleSheet()

    estilo_titulo_doc = ParagraphStyle('TituloDoc', parent=estilos['Heading1'], fontSize=18,
                                       alignment=TA_CENTER, spaceAfter=25,
                                       textColor=colors.HexColor("#1A365D"))
    estilo_h1 = ParagraphStyle('H1', parent=estilos['Heading2'], fontSize=15,
                                spaceBefore=22, spaceAfter=12,
                                textColor=colors.HexColor("#2B6CB0"))
    estilo_h2 = ParagraphStyle('H2', parent=estilos['Heading3'], fontSize=13,
                                spaceBefore=14, spaceAfter=8,
                                textColor=colors.HexColor("#2D3748"))
    estilo_bloco = ParagraphStyle('Bloco', parent=estilos['Heading3'], fontSize=12,
                                   spaceBefore=18, spaceAfter=8,
                                   textColor=colors.HexColor("#1A365D"),
                                   backColor=colors.HexColor("#EBF4FF"),
                                   borderPad=6)
    estilo_corpo = ParagraphStyle('Corpo', parent=estilos['BodyText'], fontSize=11,
                                   leading=16, textColor=colors.black)

    elementos = [Paragraph("MATERIAL DIRECIONADO PARA RESIDÊNCIA", estilo_titulo_doc)]

    in_table = False
    table_data = []

    QUEBRA_PAGINA = {"GABARITO COMENTADO", "CADERNO DE QUESTÕES"}
    BLOCOS_BANCA  = {"BLOCO USP-SP", "BLOCO SUS-SP", "BLOCO ENAMED",
                     "BLOCO USP SP", "BLOCO SUS SP"}

    for linha in markdown_text.split('\n'):
        linha_limpa = linha.strip()

        if not linha_limpa:
            if in_table:
                table_data = _fechar_tabela_pendente(elementos, table_data, estilo_corpo)
                in_table = False
            elementos.append(Spacer(1, 6))
            continue

        if linha_limpa.startswith('|') and linha_limpa.endswith('|'):
            if '---' in linha_limpa:
                continue
            in_table = True
            celulas = [c.strip() for c in linha_limpa.split('|')[1:-1]]
            table_data.append([Paragraph(_formatar_texto_celula(c), estilo_corpo) for c in celulas])
            continue

        if in_table:
            table_data = _fechar_tabela_pendente(elementos, table_data, estilo_corpo)
            in_table = False

        linha_upper = linha_limpa.upper()

        if any(k in linha_upper for k in QUEBRA_PAGINA):
            elementos.append(PageBreak())

        conteudo_raw = re.sub(r'^#+\s*', '', linha_limpa)

        if linha_limpa.startswith('### '):
            elementos.append(Paragraph(_formatar_texto_celula(conteudo_raw), estilo_h2))
        elif linha_limpa.startswith('## '):
            if any(k in linha_upper for k in BLOCOS_BANCA):
                elementos.append(Paragraph(_formatar_texto_celula(conteudo_raw), estilo_bloco))
            else:
                elementos.append(Paragraph(_formatar_texto_celula(conteudo_raw), estilo_h2))
        elif linha_limpa.startswith('# '):
            elementos.append(Paragraph(_formatar_texto_celula(conteudo_raw), estilo_h1))
        elif linha_limpa.startswith('- ') or linha_limpa.startswith('* '):
            elementos.append(Paragraph("• " + _formatar_texto_celula(linha_limpa[2:]), estilo_corpo))
        else:
            elementos.append(Paragraph(_formatar_texto_celula(linha_limpa), estilo_corpo))

    if in_table:
        _fechar_tabela_pendente(elementos, table_data, estilo_corpo)

    doc.build(elementos)


class AplicativoMedCel(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Assistente de Transcrição Médica")
        self.geometry("600x750")
        self.diretorio_salvamento = DIRETORIO_BASE

        self.cliente_gemini = None
        if CHAVE_API_GEMINI:
            self.cliente_gemini = _criar_cliente_gemini()

        ctk.CTkLabel(self, text="Transcritor de Aulas", font=("Arial", 20, "bold")).pack(pady=10)
        
        frame_qtd = ctk.CTkFrame(self, fg_color="transparent")
        frame_qtd.pack(pady=5)
        ctk.CTkLabel(frame_qtd, text="Quantidade de Aulas:").pack(side="left", padx=5)
        self.menu_qtd = ctk.CTkOptionMenu(frame_qtd, values=["1", "2", "3", "4"], 
                                          command=self.atualizar_campos_url, width=80)
        self.menu_qtd.pack(side="left", padx=5)
        
        self.frame_urls = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_urls.pack(pady=5)
        
        self.entradas_url = []
        self.atualizar_campos_url("1")
        
        self.input_nome = ctk.CTkEntry(self, placeholder_text="Nome do Documento (Ex: Cirurgia_Geral)", width=450)
        self.input_nome.pack(pady=10)

        self.frame_dir = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_dir.pack(pady=5)
        self.input_dir = ctk.CTkEntry(self.frame_dir, width=330)
        self.input_dir.insert(0, self.diretorio_salvamento)
        self.input_dir.configure(state="disabled")
        self.input_dir.pack(side="left", padx=5)
        ctk.CTkButton(self.frame_dir, text="Pasta", width=100,
                      command=self.escolher_diretorio).pack(side="right")

        self.botao_iniciar = ctk.CTkButton(self, text="Gerar Material e Questões",
                                            command=self.iniciar_processamento)
        self.botao_iniciar.pack(pady=15)

        self.barra_progresso = ctk.CTkProgressBar(self, width=400, mode="indeterminate")
        self.barra_progresso.pack(pady=5)
        self.barra_progresso.set(0)

        self.label_status = ctk.CTkLabel(self, text="", text_color="gray")
        self.label_status.pack(pady=5)

        self.caixa_texto = ctk.CTkTextbox(self, width=500, height=180)
        self.caixa_texto.pack(pady=10)

    def atualizar_campos_url(self, valor):
        qtd = int(valor)
        for widget in self.frame_urls.winfo_children():
            widget.destroy()
        self.entradas_url.clear()
        
        for i in range(qtd):
            entrada = ctk.CTkEntry(self.frame_urls, placeholder_text=f"Link da Aula {i+1} (.m3u8)", width=450)
            entrada.pack(pady=5)
            self.entradas_url.append(entrada)

    def escolher_diretorio(self):
        d = filedialog.askdirectory()
        if d:
            self.diretorio_salvamento = d
            self.input_dir.configure(state="normal")
            self.input_dir.delete(0, 'end')
            self.input_dir.insert(0, d)
            self.input_dir.configure(state="disabled")

    def iniciar_processamento(self):
        urls = [entrada.get().strip() for entrada in self.entradas_url if entrada.get().strip()]
        n = self.input_nome.get().strip()
        
        if not urls:
            self.label_status.configure(text="Erro: Nenhum link fornecido.", text_color="red")
            return
        if not CHAVE_API_GEMINI or not CHAVE_API_GROQ:
            self.label_status.configure(text="Erro: Chaves API ausentes no .env", text_color="red")
            return

        if self.cliente_gemini is None:
            self.cliente_gemini = _criar_cliente_gemini()

        self.botao_iniciar.configure(state="disabled")
        self.menu_qtd.configure(state="disabled")
        for entrada in self.entradas_url:
            entrada.configure(state="disabled")
            
        self.barra_progresso.start()
        threading.Thread(target=self.executar_pipeline,
                         args=(urls, n, self.diretorio_salvamento)).start()

    def executar_pipeline(self, urls, nome, diretorio):
        try:
            texto_bruto_acumulado = ""
            
            for i, url in enumerate(urls):
                self.label_status.configure(text=f"Baixando áudio {i+1}/{len(urls)}...")
                mp3 = baixar_audio_do_link(url)

                self.label_status.configure(text=f"Transcrevendo áudio {i+1}/{len(urls)} via Groq...")
                raw = transcrever_audio_nuvem(mp3)
                
                texto_bruto_acumulado += f"\n\n--- INÍCIO DA TRANSCRIÇÃO DA AULA {i+1} ---\n{raw}\n--- FIM DA TRANSCRIÇÃO DA AULA {i+1} ---\n"

                if os.path.exists(mp3):
                    os.remove(mp3)

            self.label_status.configure(text="Gemini 2.5 Pro: Gerando Resumo Teórico Integrado... (1/2)")
            resumo, uso_resumo = gerar_resumo_teorico(self.cliente_gemini, texto_bruto_acumulado)
            if resumo.startswith("Falha_Crítica:"):
                raise Exception(resumo)

            self.label_status.configure(text="Gemini 2.5 Pro: Gerando Questões por Banca... (2/2)")
            questoes, uso_questoes = gerar_questoes_e_gabarito(self.cliente_gemini, texto_bruto_acumulado)
            if questoes.startswith("Falha_Crítica:"):
                raise Exception(questoes)

            material_final = resumo + "\n\n" + questoes

            self.label_status.configure(text="Compilando PDF Final...")
            arq = f"{nome.replace(' ', '_') if nome else 'estudo_integrado'}.pdf"
            caminho = os.path.join(diretorio, arq)
            compilar_pdf_estudo(material_final, caminho)

            log_consumo = _calcular_log_consumo(uso_resumo, uso_questoes)
            self.caixa_texto.delete("0.0", "end")
            self.caixa_texto.insert("0.0", log_consumo + material_final)
            self.label_status.configure(text=f"Sucesso: {arq}", text_color="#2ECC71")

        except Exception as e:
            self.label_status.configure(text="Erro de Execução. Veja o log abaixo.",
                                         text_color="red")
            self.caixa_texto.delete("0.0", "end")
            self.caixa_texto.insert("0.0", str(e))
        finally:
            self.barra_progresso.stop()
            self.barra_progresso.set(0)
            self.botao_iniciar.configure(state="normal")
            self.menu_qtd.configure(state="normal")
            for entrada in self.entradas_url:
                entrada.configure(state="normal")
            for lixo in glob.glob(os.path.join(DIRETORIO_BASE, 'audio_temporario.*')):
                try:
                    os.remove(lixo)
                except:
                    pass


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    AplicativoMedCel().mainloop()