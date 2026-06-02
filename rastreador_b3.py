import yfinance as yf
import pandas as pd
import requests
import json
import csv
import os
from datetime import datetime

ARQUIVO_ATIVOS = "ativos.txt"
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK", "")

def carregar_carteira():
    if not os.path.exists(ARQUIVO_ATIVOS):
        with open(ARQUIVO_ATIVOS, 'w') as f:
            f.write("PETR4.SA\nVALE3.SA\nITUB4.SA\nWEGE3.SA\n")
    with open(ARQUIVO_ATIVOS, 'r') as f:
        return [linha.strip() for linha in f if linha.strip() and not linha.startswith('#')]

def enviar_discord(mensagem, cor=0x00ff00):
    if not DISCORD_WEBHOOK_URL:
        print("URL não configurada")
        return False
    payload = {"content": None, "embeds": [{"title": "Alerta B3", "description": mensagem, "color": cor}]}
    try:
        r = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        if r.status_code == 204:
            print("Enviado ao Discord")
            return True
        else:
            print(f"Erro Discord: {r.status_code} - {r.text}")
            return False
    except Exception as e:
        print(f"Exceção Discord: {e}")
        return False

def analisar_ativo(ticker):
    try:
        t = yf.Ticker(ticker)
        df = t.history(period="6mo")
        if df.empty: return None
        df = df[['Close']].copy()
        df.columns = ['preco_fechamento']
        df['EMA_9'] = df['preco_fechamento'].ewm(span=9, adjust=False).mean()
        df['EMA_21'] = df['preco_fechamento'].ewm(span=21, adjust=False).mean()
        df['Sinal_Compra'] = (df['EMA_9'] > df['EMA_21']) & (df['EMA_9'].shift(1) <= df['EMA_21'].shift(1))
        df['Sinal_Venda'] = (df['EMA_9'] < df['EMA_21']) & (df['EMA_9'].shift(1) >= df['EMA_21'].shift(1))
        return df.iloc[-1]
    except Exception as e:
        print(f"Erro {ticker}: {e}")
        return None

def rodar_rastreador():
    print(f"Iniciando {datetime.now()}")
    ativos = carregar_carteira()
    for ativo in ativos:
        ult = analisar_ativo(ativo)
        if ult is None: continue
        preco = ult['preco_fechamento']
        ticker_limpo = ativo.split('.')[0]
        if ult['Sinal_Compra']:
            enviar_discord(f"🟢 {ticker_limpo} - COMPRA\nR$ {preco:.2f}", cor=0x00ff00)
        elif ult['Sinal_Venda']:
            enviar_discord(f"🔴 {ticker_limpo} - VENDA\nR$ {preco:.2f}", cor=0xff0000)
        else:
            print(f"{ticker_limpo}: Sem sinal (R$ {preco:.2f})")
    print("Fim")

if __name__ == "__main__":
    rodar_rastreador()
