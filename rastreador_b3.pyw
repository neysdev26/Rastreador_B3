import yfinance as yf
import pandas as pd
import requests
import json
import csv
import os
from datetime import datetime
import time

# ==========================================
# CONFIGURAÇÕES GERAIS
# ==========================================
# Arquivo texto que servirá como sua carteira de monitoramento
ARQUIVO_ATIVOS = "ativos.txt"

# Parâmetros das médias móveis exponenciais (EMAs)
EMA_RAPIDA = 9
EMA_LENTA = 21

# Webhook do Discord (Caso não configurado na variável de ambiente, preencha diretamente aqui)
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK", "SUA_URL_DO_WEBHOOK_AQUI")

def carregar_carteira():
    """
    Lê os tickers do arquivo 'ativos.txt'.
    Caso o arquivo não exista, cria um arquivo padrão com ações sugeridas.
    """
    if not os.path.exists(ARQUIVO_ATIVOS):
        with open(ARQUIVO_ATIVOS, 'w', encoding='utf-8') as f:
            f.write("# Adicione um ativo por linha (precisa do sufixo .SA para a B3)\n")
            f.write("PETR4.SA\nVALE3.SA\nITUB4.SA\nWEGE3.SA\n")
    
    with open(ARQUIVO_ATIVOS, 'r', encoding='utf-8') as f:
        # Retorna apenas as linhas que não são vazias nem comentários
        return [linha.strip() for linha in f if linha.strip() and not linha.startswith('#')]

def analisar_ativo(ticker):
    """
    Consome os dados históricos da API do Yahoo Finance,
    calcula as Médias Móveis Exponenciais e identifica os sinais de compra ou venda.
    """
    print(f"📥 Coletando dados históricos de {ticker}...")
    try:
        ticker_obj = yf.Ticker(ticker)
        # 6 meses de histórico garantem dados suficientes para calcular a média de 21 sem distorção inicial
        df = ticker_obj.history(period="6mo")
        if df.empty:
            print(f"❌ Sem dados disponíveis para o ativo: {ticker}")
            return None

        # Limpamos o DataFrame para manter apenas o preço de fechamento
        df = df[['Close']].copy()
        df.columns = ['preco_fechamento']

        # Cálculo das médias móveis exponenciais (EMA)
        df['EMA_rapida'] = df['preco_fechamento'].ewm(span=EMA_RAPIDA, adjust=False).mean()
        df['EMA_lenta'] = df['preco_fechamento'].ewm(span=EMA_LENTA, adjust=False).mean()

        # Condição de cruzamento:
        # Sinal de Compra: Rápida cruzou para CIMA da Lenta hoje, mas ontem estava abaixo ou igual.
        df['Sinal_Compra'] = (df['EMA_rapida'] > df['EMA_lenta']) & (df['EMA_rapida'].shift(1) <= df['EMA_lenta'].shift(1))
        
        # Sinal de Venda: Rápida cruzou para BAIXO da Lenta hoje, mas ontem estava acima ou igual.
        df['Sinal_Venda'] = (df['EMA_rapida'] < df['EMA_lenta']) & (df['EMA_rapida'].shift(1) >= df['EMA_lenta'].shift(1))

        return df
    except Exception as e:
        print(f"❌ Erro crítico ao processar {ticker}: {e}")
        return None

def salvar_alerta(ticker, preco, tipo):
    """
    Registra o sinal disparado em uma planilha local chamada 'alertas.csv'.
    """
    arquivo_existe = os.path.exists('alertas.csv')
    with open('alertas.csv', 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        # Escreve o cabeçalho caso o arquivo seja novo ou esteja vazio
        if not arquivo_existe or os.stat('alertas.csv').st_size == 0:
            writer.writerow(['Data', 'Ticker', 'Preço', 'Sinal'])
        
        writer.writerow([
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            ticker,
            f"{preco:.2f}",
            tipo
        ])

def enviar_discord_melhorado(ticker, preco, tipo, estrategia, cor):
    """
    Prepara e envia um card visual premium (Rich Embed) ao canal do Discord
    configurado, contendo formatações avançadas, links úteis e tags.
    """
    if not DISCORD_WEBHOOK_URL or DISCORD_WEBHOOK_URL in ["SUA_URL_DO_WEBHOOK_AQUI", ""]:
        print("⚠️ Notificação Discord ignorada: Webhook não configurado.")
        return

    emoji = "🟢" if tipo == "COMPRA" else "🔴"
    status_texto = "SINAL DE COMPRA" if tipo == "COMPRA" else "SINAL DE VENDA"
    
    # Estruturação visual do Card Embed no Discord
    payload = {
        "embeds": [{
            "title": f"{emoji} {ticker} - {status_texto}",
            "description": f"O robô rastreador técnico detectou um novo gatilho operacional para o ativo **{ticker}**.",
            "color": cor,
            "fields": [
                {
                    "name": "💰 Preço de Disparo",
                    "value": f"```Gherkin\nR$ {preco:.2f}\n```",
                    "inline": True
                },
                {
                    "name": "📈 Estratégia Utilizada",
                    "value": f"```📌 {estrategia}\n```",
                    "inline": True
                },
                {
                    "name": "🔗 Links de Apoio",
                    "value": f"[Gráfico TradingView](https://br.tradingview.com/symbols/BMFBOVESPA-{ticker}/) | [Status Invest](https://statusinvest.com.br/acoes/{ticker.lower()})",
                    "inline": False
                }
            ],
            "timestamp": datetime.now().isoformat(),
            "footer": {
                "text": "🤖 Rastreador B3 | Inteligência Algorítmica",
                "icon_url": "https://i.imgur.com/w8R6c5H.png"  # Ícone ilustrativo de robô para o rodapé
            }
        }]
    }

    try:
        resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        if resp.status_code == 204:
            print(f"✅ Notificação de {ticker} enviada com sucesso ao Discord!")
        else:
            print(f"❌ Erro do Discord ({resp.status_code}): {resp.text}")
    except Exception as e:
        print(f"⚠️ Erro de conexão ao disparar alerta ao Discord: {e}")

def rodar_rastreador():
    """
    Função principal que orquestra a varredura em todos os ativos da carteira.
    """
    print(f"\n--- Varredura iniciada em {datetime.now().strftime('%d/%m/%Y %H:%M')} ---")
    carteira = carregar_carteira()
    
    if not carteira:
        print("⚠️ A lista de monitoramento está vazia. Adicione ativos ao arquivo 'ativos.txt'.")
        return

    for ticker in carteira:
        df = analisar_ativo(ticker)
        if df is None:
            continue

        # Obtém o último candle fechado (último dia de negociação do mercado)
        ultima_linha = df.iloc[-1]
        preco_fechamento = ultima_linha['preco_fechamento']
        ticker_limpo = ticker.split('.')[0]

        if ultima_linha['Sinal_Compra']:
            estrategia_msg = f"EMA {EMA_RAPIDA} cruzou ACIMA da EMA {EMA_LENTA}"
            print(f"📢 🟢 COMPRA IDENTIFICADA: {ticker_limpo} a R$ {preco_fechamento:.2f}")
            
            # Envia o alerta formatado em Verde Esmeralda (0x2ecc71)
            enviar_discord_melhorado(ticker_limpo, preco_fechamento, 'COMPRA', estrategia_msg, cor=0x2ecc71)
            salvar_alerta(ticker_limpo, preco_fechamento, 'COMPRA')

        elif ultima_linha['Sinal_Venda']:
            estrategia_msg = f"EMA {EMA_RAPIDA} cruzou ABAIXO da EMA {EMA_LENTA}"
            print(f"📢 🔴 VENDA IDENTIFICADA: {ticker_limpo} a R$ {preco_fechamento:.2f}")
            
            # Envia o alerta formatado em Vermelho Alizarin (0xe74c3c)
            enviar_discord_melhorado(ticker_limpo, preco_fechamento, 'VENDA', estrategia_msg, cor=0xe74c3c)
            salvar_alerta(ticker_limpo, preco_fechamento, 'VENDA')

        else:
            print(f"ℹ️ {ticker_limpo}: R$ {preco_fechamento:.2f} | Sem cruzamentos ou sinais de alerta hoje.")

    print("--- Varredura de mercado concluída com sucesso! ---\n")

if __name__ == "__main__":
    # EXECUÇÃO CONTÍNUA:
    # O bloco abaixo roda continuamente monitorando os preços e recalculando de 5 em 5 minutos.
    try:
        while True:
            rodar_rastreador()
            print("⏳ Aguardando 5 minutos para a próxima varredura de mercado...")
            time.sleep(300)
    except KeyboardInterrupt:
        print("\n👋 Execução interrompida manualmente pelo usuário. Até logo!")

### O que mudou e como usar:
1. **Layout Premium Ativo:** Os alertas agora chegam no Discord em formato de cards estruturados com as cores exatas (verde para compra, vermelho para venda), blocos de código cinza escuro para isolar os dados técnicos e links rápidos para análise.
2. **Histórico Local Garantido:** Sempre que um sinal for enviado ao Discord, ele também será catalogado no arquivo local `alertas.csv` para que você possa auditar os resultados depois.
3. **Execução Contínua Segura:** O script agora conta com um controle de parada suave (`KeyboardInterrupt`), permitindo que você pare a execução a qualquer momento pressionando `Ctrl + C` no terminal.
