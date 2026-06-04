import yfinance as yf
import pandas as pd
import requests
import csv
import os
from datetime import datetime

# ==========================================
# CONFIGURAÇÕES
# ==========================================
ARQUIVO_ATIVOS = "ativos.txt"
ARQUIVO_ALERTAS = "alertas.csv"
EMA_RAPIDA_DEFAULT = 9
EMA_LENTA_DEFAULT = 21
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK", "")

# ==========================================
# FUNÇÕES AUXILIARES
# ==========================================
def carregar_carteira():
    if not os.path.exists(ARQUIVO_ATIVOS):
        with open(ARQUIVO_ATIVOS, 'w') as f:
            f.write("PETR4.SA\nVALE3.SA\nITUB4.SA\nWEGE3.SA\n")
    with open(ARQUIVO_ATIVOS, 'r') as f:
        return [linha.strip() for linha in f if linha.strip() and not linha.startswith('#')]

def analisar_ativo_rastreador(ticker, ema_r=EMA_RAPIDA_DEFAULT, ema_l=EMA_LENTA_DEFAULT):
    """Retorna um dicionário com dados completos do último dia e indicadores."""
    try:
        t = yf.Ticker(ticker)
        df = t.history(period="6mo")
        if df.empty:
            return None

        close = df['Close']
        open_ = df['Open']
        high = df['High']
        low = df['Low']
        volume = df['Volume']

        ema_rapida = close.ewm(span=ema_r, adjust=False).mean()
        ema_lenta = close.ewm(span=ema_l, adjust=False).mean()

        sinal_compra = (ema_rapida > ema_lenta) & (ema_rapida.shift(1) <= ema_lenta.shift(1))
        sinal_venda = (ema_rapida < ema_lenta) & (ema_rapida.shift(1) >= ema_lenta.shift(1))

        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        ultimo = df.index[-1]
        preco = close.iloc[-1]
        abertura = open_.iloc[-1]
        maxima = high.iloc[-1]
        minima = low.iloc[-1]
        vol = volume.iloc[-1]
        rsi_val = rsi.iloc[-1]

        preco_anterior = close.iloc[-2] if len(close) > 1 else preco
        variacao = (preco - preco_anterior) / preco_anterior * 100

        return {
            'ticker': ticker,
            'preco': preco,
            'abertura': abertura,
            'maxima': maxima,
            'minima': minima,
            'variacao': variacao,
            'volume': vol,
            'rsi': rsi_val,
            'sinal_compra': sinal_compra.iloc[-1],
            'sinal_venda': sinal_venda.iloc[-1],
            'ema_rapida': ema_rapida.iloc[-1],
            'ema_lenta': ema_lenta.iloc[-1],
            'data': ultimo
        }
    except Exception as e:
        print(f"Erro ao processar {ticker}: {e}")
        return None

def enviar_discord(dados, tipo):
    """Envia embed rico e completo para o Discord."""
    if not DISCORD_WEBHOOK_URL:
        return False

    if tipo == 'COMPRA':
        cor = 0x00ff00
        emoji = "🟢"
        acao = "COMPRA"
    else:
        cor = 0xff0000
        emoji = "🔴"
        acao = "VENDA"

    ticker_limpo = dados['ticker'].split('.')[0]
    preco = dados['preco']
    abertura = dados['abertura']
    maxima = dados['maxima']
    minima = dados['minima']
    variacao = dados['variacao']
    volume = dados['volume']
    rsi = dados['rsi']

    # Formata volume
    if volume and volume > 0:
        if volume >= 1e6:
            vol_str = f"{volume/1e6:.1f}M"
        elif volume >= 1e3:
            vol_str = f"{volume/1e3:.0f}K"
        else:
            vol_str = f"{volume:.0f}"
    else:
        vol_str = "N/D"

    descricao = (
        f"{emoji} **{ticker_limpo} - SINAL DE {acao}**\n"
        f"💰 **Fechamento:** R$ {preco:.2f} ({variacao:+.2f}%)\n"
        f"📈 **Abertura:** R$ {abertura:.2f}\n"
        f"📊 **Máxima:** R$ {maxima:.2f}  |  **Mínima:** R$ {minima:.2f}\n"
        f"📦 **Volume:** {vol_str}\n"
        f"📉 **RSI (14):** {rsi:.1f}"
    )

    embed = {
        "title": "Alerta do Rastreador B3",
        "description": descricao,
        "color": cor,
        "fields": [
            {
                "name": "🧠 Estratégia",
                "value": f"EMA {EMA_RAPIDA_DEFAULT} cruzou **{'ACIMA' if tipo=='COMPRA' else 'ABAIXO'}** da EMA {EMA_LENTA_DEFAULT}",
                "inline": False
            }
        ],
        "timestamp": dados['data'].isoformat(),
        "footer": {"text": "Sistema de Análise Técnica • Apenas informativo"}
    }

    payload = {"embeds": [embed]}

    try:
        resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        if resp.status_code == 204:
            print("✅ Alerta enviado ao Discord!")
            return True
        else:
            print(f"❌ Erro Discord: {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        print(f"⚠️ Exceção Discord: {e}")
        return False

def salvar_alerta(ticker, preco, tipo):
    """Registra o sinal em alertas.csv."""
    arquivo_existe = os.path.exists(ARQUIVO_ALERTAS)
    with open(ARQUIVO_ALERTAS, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not arquivo_existe or os.stat(ARQUIVO_ALERTAS).st_size == 0:
            writer.writerow(['Data', 'Ticker', 'Preço', 'Sinal'])
        writer.writerow([
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            ticker,
            f"{preco:.2f}",
            tipo
        ])

# ==========================================
# EXECUÇÃO PRINCIPAL
# ==========================================
def rodar_rastreador():
    print(f"--- Varredura iniciada em {datetime.now().strftime('%d/%m/%Y %H:%M')} ---")

    # 🧪 TESTE FORÇADO (remova este bloco após confirmar que o Discord está funcionando)
    dados_teste = {
        'ticker': 'TESTE.SA',
        'preco': 99.99,
        'abertura': 99.00,
        'maxima': 100.50,
        'minima': 98.50,
        'variacao': 1.23,
        'volume': 1_500_000,
        'rsi': 58.4,
        'data': datetime.now()
    }
    enviar_discord(dados_teste, 'COMPRA')
    # -----------------------------------------------------------

    ativos = carregar_carteira()
    if not ativos:
        print("⚠️ Carteira vazia.")
        return

    for ticker in ativos:
        dados = analisar_ativo_rastreador(ticker)
        if dados is None:
            continue

        ticker_limpo = ticker.split('.')[0]
        if dados['sinal_compra']:
            print(f"📢 Sinal de COMPRA detectado para {ticker_limpo}")
            enviar_discord(dados, 'COMPRA')
            salvar_alerta(ticker_limpo, dados['preco'], 'COMPRA')
        elif dados['sinal_venda']:
            print(f"📢 Sinal de VENDA detectado para {ticker_limpo}")
            enviar_discord(dados, 'VENDA')
            salvar_alerta(ticker_limpo, dados['preco'], 'VENDA')
        else:
            print(f"ℹ️ {ticker_limpo}: R$ {dados['preco']:.2f} | Sem sinal.")

    print("--- Varredura concluída ---")

if __name__ == "__main__":
    rodar_rastreador()