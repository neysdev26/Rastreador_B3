import yfinance as yf
import pandas as pd
import requests
import json
import csv
import os
from datetime import datetime
import time


# ==========================================
# CONFIGURAÇÕES
# ==========================================
# Arquivo com a lista de tickers (um por linha)
ARQUIVO_ATIVOS = "ativos.txt"

# Parâmetros das médias móveis (ajuste conforme necessário)
EMA_RAPIDA = 9
EMA_LENTA = 21

# Webhook do Discord (substitua pela sua URL)
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1509918416008515654/TuvG64GT0ye6qGicCA8ib1ScsSdKkUZWo5NSvbxDUl-ruhdzqqSoTIsn7uCKB0S1o7lx"

# ==========================================
# FUNÇÕES AUXILIARES
# ==========================================
def carregar_carteira():
    """Lê os tickers do arquivo, criando um padrão se necessário."""
    if not os.path.exists(ARQUIVO_ATIVOS):
        with open(ARQUIVO_ATIVOS, 'w') as f:
            f.write("PETR4.SA\nVALE3.SA\nITUB4.SA\nWEGE3.SA\n")
    with open(ARQUIVO_ATIVOS, 'r') as f:
        # Ignora linhas vazias e comentários
        return [linha.strip() for linha in f if linha.strip() and not linha.startswith('#')]

def analisar_ativo(ticker):
    """Coleta dados históricos e calcula indicadores."""
    print(f"📥 Coletando dados para {ticker}...")
    try:
        ticker_obj = yf.Ticker(ticker)
        df = ticker_obj.history(period="6mo")
        if df.empty:
            print(f"❌ Sem dados para {ticker}")
            return None

        df = df[['Close']].copy()
        df.columns = ['preco_fechamento']

        # Médias móveis exponenciais
        df['EMA_rapida'] = df['preco_fechamento'].ewm(span=EMA_RAPIDA, adjust=False).mean()
        df['EMA_lenta'] = df['preco_fechamento'].ewm(span=EMA_LENTA, adjust=False).mean()

        # Sinais de cruzamento
        df['Sinal_Compra'] = (df['EMA_rapida'] > df['EMA_lenta']) & (df['EMA_rapida'].shift(1) <= df['EMA_lenta'].shift(1))
        df['Sinal_Venda'] = (df['EMA_rapida'] < df['EMA_lenta']) & (df['EMA_rapida'].shift(1) >= df['EMA_lenta'].shift(1))

        return df
    except Exception as e:
        print(f"❌ Erro ao processar {ticker}: {e}")
        return None

def salvar_alerta(ticker, preco, tipo):
    """Registra o sinal em alertas.csv."""
    arquivo_existe = os.path.exists('alertas.csv')
    with open('alertas.csv', 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not arquivo_existe or os.stat('alertas.csv').st_size == 0:
            writer.writerow(['Data', 'Ticker', 'Preço', 'Sinal'])
        writer.writerow([
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            ticker,
            f"{preco:.2f}",
            tipo
        ])

def enviar_discord(mensagem, cor=0x00ff00):
    """Envia um alerta em embed para o Discord."""
    if DISCORD_WEBHOOK_URL == "https://discord.com/api/webhooks/1509918416008515654/TuvG64GT0ye6qGicCA8ib1ScsSdKkUZWo5NSvbxDUl-ruhdzqqSoTIsn7uCKB0S1o7lx":
        print("⚠️ URL do Discord não configurada.")
        return

    payload = {
        "embeds": [{
            "title": "Alerta do Rastreador B3",
            "description": mensagem,
            "color": cor,
            "timestamp": datetime.now().isoformat(),
            "footer": {"text": "Sistema de Análise Técnica"}
        }]
    }
    try:
        resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        if resp.status_code == 204:
            print("✅ Alerta enviado ao Discord!")
        else:
            print(f"❌ Falha no Discord: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"⚠️ Erro de conexão com Discord: {e}")

# ==========================================
# EXECUÇÃO PRINCIPAL
# ==========================================
def rodar_rastreador():
    print(f"--- Varredura iniciada em {datetime.now().strftime('%d/%m/%Y %H:%M')} ---")
    carteira = carregar_carteira()
    if not carteira:
        print("⚠️ Carteira vazia. Adicione tickers em ativos.txt")
        return

    for ticker in carteira:
        df = analisar_ativo(ticker)
        if df is None:
            continue

        ultima = df.iloc[-1]
        preco = ultima['preco_fechamento']
        ticker_limpo = ticker.split('.')[0]

        if ultima['Sinal_Compra']:
            msg = (f"🟢 **{ticker_limpo}** - SINAL DE COMPRA\n"
                   f"💰 Preço: R$ {preco:.2f}\n"
                   f"📈 EMA {EMA_RAPIDA} cruzou ACIMA da EMA {EMA_LENTA}")
            print(f"📢 {msg}")
            enviar_discord(msg, cor=0x00ff00)   # verde
            salvar_alerta(ticker_limpo, preco, 'COMPRA')

        elif ultima['Sinal_Venda']:
            msg = (f"🔴 **{ticker_limpo}** - SINAL DE VENDA\n"
                   f"💰 Preço: R$ {preco:.2f}\n"
                   f"📉 EMA {EMA_RAPIDA} cruzou ABAIXO da EMA {EMA_LENTA}")
            print(f"📢 {msg}")
            enviar_discord(msg, cor=0xff0000)   # vermelho
            salvar_alerta(ticker_limpo, preco, 'VENDA')

        else:
            print(f"ℹ️ {ticker_limpo}: R$ {preco:.2f} | Sem sinal no momento.")

    print("--- Varredura concluída ---\n")

if __name__ == "__main__":
    # Para execução contínua (ex.: a cada 5 min)

    while True:
        rodar_rastreador()
        print("⏳ Aguardando 5 minutos...")
        time.sleep(300)

    # Execução única:
    rodar_rastreador()