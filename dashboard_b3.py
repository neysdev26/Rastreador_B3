import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import os
import requests
import json
import csv
import time

# ==========================================
# CONFIGURAÇÕES INICIAIS
# ==========================================
st.set_page_config(page_title="Dashboard B3", page_icon="📈", layout="wide")

# Arquivos compartilhados
ARQUIVO_ATIVOS = "ativos.txt"
ARQUIVO_ALERTAS = "alertas.csv"

# Parâmetros das médias móveis (padrão)
EMA_RAPIDA_DEFAULT = 9
EMA_LENTA_DEFAULT = 21

# Webhook do Discord (será substituído por segredo no Streamlit Cloud)
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK", "")

# ==========================================
# FUNÇÕES DE CARTEIRA
# ==========================================
def carregar_carteira():
    if not os.path.exists(ARQUIVO_ATIVOS):
        with open(ARQUIVO_ATIVOS, 'w') as f:
            f.write("PETR4.SA\nVALE3.SA\nITUB4.SA\nWEGE3.SA\n")
    with open(ARQUIVO_ATIVOS, 'r') as f:
        return [linha.strip() for linha in f if linha.strip() and not linha.startswith('#')]

def salvar_carteira(lista):
    with open(ARQUIVO_ATIVOS, 'w') as f:
        for t in lista:
            f.write(f"{t}\n")

# ==========================================
# FUNÇÕES DE ANÁLISE (gráficos)
# ==========================================
@st.cache_data(ttl=300)
def carregar_dados(tickers, periodo, ema_r, ema_l):
    dados = {}
    for ticker in tickers:
        try:
            ticker_obj = yf.Ticker(ticker)
            df = ticker_obj.history(period=periodo)
            if df.empty:
                continue

            df[f'EMA_{ema_r}'] = df['Close'].ewm(span=ema_r, adjust=False).mean()
            df[f'EMA_{ema_l}'] = df['Close'].ewm(span=ema_l, adjust=False).mean()

            df['Sinal_Compra'] = (df[f'EMA_{ema_r}'] > df[f'EMA_{ema_l}']) & \
                                 (df[f'EMA_{ema_r}'].shift(1) <= df[f'EMA_{ema_l}'].shift(1))
            df['Sinal_Venda'] = (df[f'EMA_{ema_r}'] < df[f'EMA_{ema_l}']) & \
                                (df[f'EMA_{ema_r}'].shift(1) >= df[f'EMA_{ema_l}'].shift(1))

            delta = df['Close'].diff()
            gain = delta.clip(lower=0).rolling(14).mean()
            loss = (-delta.clip(upper=0)).rolling(14).mean()
            rs = gain / loss
            df['RSI'] = 100 - (100 / (1 + rs))

            df['BB_media'] = df['Close'].rolling(20).mean()
            bb_std = df['Close'].rolling(20).std()
            df['BB_superior'] = df['BB_media'] + 2 * bb_std
            df['BB_inferior'] = df['BB_media'] - 2 * bb_std

            ema12 = df['Close'].ewm(span=12, adjust=False).mean()
            ema26 = df['Close'].ewm(span=26, adjust=False).mean()
            df['MACD'] = ema12 - ema26
            df['MACD_Sinal'] = df['MACD'].ewm(span=9, adjust=False).mean()
            df['MACD_Hist'] = df['MACD'] - df['MACD_Sinal']

            dados[ticker] = df
        except Exception as e:
            st.error(f"Erro ao carregar {ticker}: {e}")
    return dados

def criar_grafico_principal(df, ticker, ema_r, ema_l, mostrar_sinais=True):
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.6, 0.2, 0.2],
        subplot_titles=(f"📈 {ticker}", "📊 Volume", "📉 RSI (14)")
    )

    fig.add_trace(go.Candlestick(
        x=df.index, open=df['Open'], high=df['High'],
        low=df['Low'], close=df['Close'], name='OHLC',
        increasing_line_color='#26a69a', decreasing_line_color='#ef5350'
    ), row=1, col=1)

    fig.add_trace(go.Scatter(x=df.index, y=df[f'EMA_{ema_r}'],
                             name=f'EMA {ema_r}', line=dict(color='#FFD700', width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df[f'EMA_{ema_l}'],
                             name=f'EMA {ema_l}', line=dict(color='#FF6B6B', width=1.5)), row=1, col=1)

    fig.add_trace(go.Scatter(x=df.index, y=df['BB_superior'],
                             line=dict(color='gray', width=1, dash='dash'), name='BB Superior'), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['BB_inferior'],
                             line=dict(color='gray', width=1, dash='dash'),
                             fill='tonexty', name='BB Inferior'), row=1, col=1)

    if mostrar_sinais:
        compras = df[df['Sinal_Compra']]
        vendas = df[df['Sinal_Venda']]
        fig.add_trace(go.Scatter(x=compras.index, y=compras['Low'] * 0.98,
                                 mode='markers', name='Compra',
                                 marker=dict(symbol='triangle-up', size=12, color='green')), row=1, col=1)
        fig.add_trace(go.Scatter(x=vendas.index, y=vendas['High'] * 1.02,
                                 mode='markers', name='Venda',
                                 marker=dict(symbol='triangle-down', size=12, color='red')), row=1, col=1)

    colors = ['#26a69a' if df['Close'].iloc[i] >= df['Open'].iloc[i] else '#ef5350' for i in range(len(df))]
    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name='Volume',
                         marker_color=colors, opacity=0.5), row=2, col=1)

    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], name='RSI',
                             line=dict(color='purple', width=2)), row=3, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", opacity=0.5, row=3, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", opacity=0.5, row=3, col=1)
    fig.add_hline(y=50, line_dash="dot", line_color="gray", opacity=0.3, row=3, col=1)

    fig.update_layout(
        template='plotly_dark',
        height=800,
        hovermode='x unified',
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    fig.update_xaxes(rangeslider_visible=False)
    return fig

# ==========================================
# FUNÇÕES DO RASTREADOR (varredura + Discord)
# ==========================================
def analisar_ativo_rastreador(ticker, ema_r=EMA_RAPIDA_DEFAULT, ema_l=EMA_LENTA_DEFAULT):
    """Retorna dicionário com dados do último dia e indicadores."""
    try:
        t = yf.Ticker(ticker)
        df = t.history(period="6mo")
        if df.empty:
            return None

        close = df['Close']
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

        ultimo_idx = df.index[-1]
        preco = close.iloc[-1]
        preco_anterior = close.iloc[-2] if len(close) > 1 else preco
        variacao = (preco - preco_anterior) / preco_anterior * 100
        vol_ultimo = volume.iloc[-1]
        rsi_ultimo = rsi.iloc[-1]

        return {
            'ticker': ticker,
            'preco': preco,
            'variacao': variacao,
            'volume': vol_ultimo,
            'rsi': rsi_ultimo,
            'sinal_compra': sinal_compra.iloc[-1],
            'sinal_venda': sinal_venda.iloc[-1],
            'ema_rapida': ema_rapida.iloc[-1],
            'ema_lenta': ema_lenta.iloc[-1],
            'data': ultimo_idx
        }
    except Exception as e:
        print(f"Erro ao processar {ticker}: {e}")
        return None

def enviar_discord(dados, tipo):
    """Envia embed rico para o Discord (compra/venda)."""
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
    variacao = dados['variacao']
    volume = dados['volume']
    rsi = dados['rsi']

    embed = {
        "title": f"{emoji} SINAL DE {acao} - {ticker_limpo}",
        "color": cor,
        "fields": [
            {
                "name": "💰 Preço Atual",
                "value": f"R$ {preco:.2f} ({variacao:+.2f}%)",
                "inline": True
            },
            {
                "name": "📊 Volume",
                "value": f"{volume:,.0f}" if volume else "N/D",
                "inline": True
            },
            {
                "name": "📈 RSI (14)",
                "value": f"{rsi:.1f}",
                "inline": True
            },
            {
                "name": "🧠 Estratégia",
                "value": f"EMA {EMA_RAPIDA_DEFAULT} cruzou {'ACIMA' if tipo=='COMPRA' else 'ABAIXO'} da EMA {EMA_LENTA_DEFAULT}",
                "inline": False
            }
        ],
        "timestamp": dados['data'].isoformat(),
        "footer": {"text": "Rastreador B3 • Apenas informativo"}
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
# INTERFACE PRINCIPAL
# ==========================================
st.title("📊 Dashboard de Análise Técnica - B3")

# ----- SIDEBAR -----
st.sidebar.header("⚙️ Configurações")

# Gerenciamento da carteira
st.sidebar.subheader("📁 Carteira de Ativos")
todos_ativos = carregar_carteira()

novo = st.sidebar.text_input("Adicionar ticker (ex: BBAS3.SA):")
if st.sidebar.button("➕ Adicionar"):
    ticker_novo = novo.upper().strip()
    if ticker_novo and ticker_novo not in todos_ativos:
        todos_ativos.append(ticker_novo)
        salvar_carteira(todos_ativos)
        st.sidebar.success(f"{ticker_novo} adicionado!")
        st.rerun()
    elif ticker_novo in todos_ativos:
        st.sidebar.warning("Ticker já existe na carteira.")

if st.sidebar.button("🗑️ Limpar carteira (reset)"):
    salvar_carteira(["PETR4.SA", "VALE3.SA", "ITUB4.SA", "WEGE3.SA"])
    st.sidebar.success("Carteira resetada para o padrão.")
    st.rerun()

# Seleção para visualização
carteira_sel = st.sidebar.multiselect(
    "Ativos para visualizar:",
    options=todos_ativos,
    default=todos_ativos
)

# Parâmetros técnicos
periodo = st.sidebar.selectbox(
    "Período:",
    ["1mo", "3mo", "6mo", "1y", "2y"],
    index=2,
    format_func=lambda x: {"1mo":"1 mês","3mo":"3 meses","6mo":"6 meses","1y":"1 ano","2y":"2 anos"}[x]
)
ema_r = st.sidebar.slider("Período EMA rápida:", 5, 20, EMA_RAPIDA_DEFAULT)
ema_l = st.sidebar.slider("Período EMA lenta:", 15, 50, EMA_LENTA_DEFAULT)
mostrar_sinais = st.sidebar.checkbox("Mostrar sinais de cruzamento", value=True)

# ----- ABAS -----
tab1, tab2, tab3 = st.tabs(["📈 Análise Técnica", "🔍 Varredura de Sinais", "📋 Histórico de Alertas"])

# ==================== TAB 1 ====================
with tab1:
    if not carteira_sel:
        st.warning("Selecione pelo menos um ativo na barra lateral.")
    else:
        with st.spinner("Carregando dados..."):
            dados = carregar_dados(carteira_sel, periodo, ema_r, ema_l)

        if not dados:
            st.error("Não foi possível carregar os dados.")
        else:
            if len(dados) > 1:
                subtabs = st.tabs([t for t in dados.keys()])
                for subtab, ticker in zip(subtabs, dados.keys()):
                    with subtab:
                        df = dados[ticker]
                        ultima = df.iloc[-1]
                        penultima = df.iloc[-2]

                        col1, col2, col3, col4 = st.columns(4)
                        variacao_dia = (ultima['Close'] - penultima['Close']) / penultima['Close'] * 100
                        variacao_periodo = (ultima['Close'] - df['Close'].iloc[0]) / df['Close'].iloc[0] * 100
                        tendencia = "📈 Alta" if ultima[f'EMA_{ema_r}'] > ultima[f'EMA_{ema_l}'] else "📉 Baixa"
                        if ultima['Sinal_Compra']:
                            sinal = "🟢 Compra"
                        elif ultima['Sinal_Venda']:
                            sinal = "🔴 Venda"
                        else:
                            sinal = "⚪ Neutro"

                        col1.metric("💰 Preço Atual", f"R$ {ultima['Close']:.2f}", f"{variacao_dia:+.2f}%")
                        col2.metric("📊 Variação no Período", f"{variacao_periodo:+.2f}%")
                        col3.metric("📈 Tendência", tendencia)
                        col4.metric("🎯 Último Sinal", sinal)

                        fig = criar_grafico_principal(df, ticker, ema_r, ema_l, mostrar_sinais)
                        st.plotly_chart(fig, use_container_width=True)

                        with st.expander("📊 Estatísticas detalhadas"):
                            c1, c2 = st.columns(2)
                            with c1:
                                st.markdown("**Preço**")
                                stats = pd.DataFrame({
                                    'Métrica': ['Máxima', 'Mínima', 'Média', 'Volatilidade (%)'],
                                    'Valor': [
                                        f"R$ {df['High'].max():.2f}",
                                        f"R$ {df['Low'].min():.2f}",
                                        f"R$ {df['Close'].mean():.2f}",
                                        f"{(df['Close'].std()/df['Close'].mean()*100):.2f}%"
                                    ]
                                })
                                st.dataframe(stats, hide_index=True, use_container_width=True)
                            with c2:
                                st.markdown("**Sinais**")
                                compras = df['Sinal_Compra'].sum()
                                vendas = df['Sinal_Venda'].sum()
                                dias_alta = (df[f'EMA_{ema_r}'] > df[f'EMA_{ema_l}']).sum()
                                dias_baixa = (df[f'EMA_{ema_r}'] < df[f'EMA_{ema_l}']).sum()
                                sinais_df = pd.DataFrame({
                                    'Métrica': ['Compras', 'Vendas', 'Dias em alta', 'Dias em baixa'],
                                    'Valor': [compras, vendas, dias_alta, dias_baixa]
                                })
                                st.dataframe(sinais_df, hide_index=True, use_container_width=True)
            else:
                ticker = list(dados.keys())[0]
                df = dados[ticker]
                ultima = df.iloc[-1]
                penultima = df.iloc[-2]

                col1, col2, col3, col4 = st.columns(4)
                variacao_dia = (ultima['Close'] - penultima['Close']) / penultima['Close'] * 100
                variacao_periodo = (ultima['Close'] - df['Close'].iloc[0]) / df['Close'].iloc[0] * 100
                tendencia = "📈 Alta" if ultima[f'EMA_{ema_r}'] > ultima[f'EMA_{ema_l}'] else "📉 Baixa"
                if ultima['Sinal_Compra']:
                    sinal = "🟢 Compra"
                elif ultima['Sinal_Venda']:
                    sinal = "🔴 Venda"
                else:
                    sinal = "⚪ Neutro"

                col1.metric("💰 Preço Atual", f"R$ {ultima['Close']:.2f}", f"{variacao_dia:+.2f}%")
                col2.metric("📊 Variação no Período", f"{variacao_periodo:+.2f}%")
                col3.metric("📈 Tendência", tendencia)
                col4.metric("🎯 Último Sinal", sinal)

                fig = criar_grafico_principal(df, ticker, ema_r, ema_l, mostrar_sinais)
                st.plotly_chart(fig, use_container_width=True)

                with st.expander("📊 Estatísticas detalhadas"):
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown("**Preço**")
                        stats = pd.DataFrame({
                            'Métrica': ['Máxima', 'Mínima', 'Média', 'Volatilidade (%)'],
                            'Valor': [
                                f"R$ {df['High'].max():.2f}",
                                f"R$ {df['Low'].min():.2f}",
                                f"R$ {df['Close'].mean():.2f}",
                                f"{(df['Close'].std()/df['Close'].mean()*100):.2f}%"
                            ]
                        })
                        st.dataframe(stats, hide_index=True, use_container_width=True)
                    with c2:
                        st.markdown("**Sinais**")
                        compras = df['Sinal_Compra'].sum()
                        vendas = df['Sinal_Venda'].sum()
                        dias_alta = (df[f'EMA_{ema_r}'] > df[f'EMA_{ema_l}']).sum()
                        dias_baixa = (df[f'EMA_{ema_r}'] < df[f'EMA_{ema_l}']).sum()
                        sinais_df = pd.DataFrame({
                            'Métrica': ['Compras', 'Vendas', 'Dias em alta', 'Dias em baixa'],
                            'Valor': [compras, vendas, dias_alta, dias_baixa]
                        })
                        st.dataframe(sinais_df, hide_index=True, use_container_width=True)

# ==================== TAB 2 ====================
with tab2:
    st.header("🔍 Varredura de Sinais de Compra/Venda")
    st.markdown("Clique no botão abaixo para verificar todos os ativos da carteira e enviar alertas ao Discord (se configurado).")

    if st.button("🚀 Executar Varredura Agora", type="primary", use_container_width=True):
        with st.spinner("Analisando ativos..."):
            ativos = carregar_carteira()
            if not ativos:
                st.warning("Carteira vazia.")
            else:
                resultados = []
                sinais_encontrados = False
                for ticker in ativos:
                    dados = analisar_ativo_rastreador(ticker, ema_r, ema_l)
                    if dados is None:
                        resultados.append({'Ticker': ticker, 'Preço': 'N/D', 'Sinal': 'Erro', 'Envio Discord': '❌'})
                        continue

                    preco = dados['preco']
                    ticker_limpo = ticker.split('.')[0]
                    sinal = 'Neutro'
                    if dados['sinal_compra']:
                        sinal = '🟢 COMPRA'
                        sinais_encontrados = True
                        discord_ok = '✅' if enviar_discord(dados, 'COMPRA') else '❌'
                        salvar_alerta(ticker_limpo, preco, 'COMPRA')
                    elif dados['sinal_venda']:
                        sinal = '🔴 VENDA'
                        sinais_encontrados = True
                        discord_ok = '✅' if enviar_discord(dados, 'VENDA') else '❌'
                        salvar_alerta(ticker_limpo, preco, 'VENDA')
                    else:
                        discord_ok = '➖'

                    resultados.append({
                        'Ticker': ticker_limpo,
                        'Preço': f"R$ {preco:.2f}",
                        'Sinal': sinal,
                        'Envio Discord': discord_ok
                    })

                st.subheader("Resultados da Varredura")
                df_res = pd.DataFrame(resultados)
                st.dataframe(df_res, hide_index=True, use_container_width=True)

                if sinais_encontrados:
                    st.success("✅ Sinais detectados! Verifique o Discord e o histórico.")
                else:
                    st.info("Nenhum sinal de cruzamento detectado no momento.")

# ==================== TAB 3 ====================
with tab3:
    st.header("📋 Histórico de Alertas Salvos")
    if os.path.exists(ARQUIVO_ALERTAS):
        df_alertas = pd.read_csv(ARQUIVO_ALERTAS)
        if not df_alertas.empty:
            df_alertas = df_alertas.sort_values('Data', ascending=False)
            st.dataframe(df_alertas, hide_index=True, use_container_width=True)
        else:
            st.info("Nenhum alerta registrado até o momento.")
    else:
        st.info("Arquivo de alertas ainda não foi criado. Execute uma varredura.")

# Rodapé
st.markdown("---")
st.caption(f"🕒 Última atualização: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} | "
           "⚠️ Apenas para fins informativos – não é recomendação de investimento.")