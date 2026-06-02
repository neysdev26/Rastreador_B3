@echo off
cd /d "C:\Users\Ney\Desktop\PROJETO\Rastreador_B3"

REM Inicia o dashboard em uma janela separada
python -m streamlit run dashboard_b3.py

REM Inicia o rastreador em loop infinito (a cada 15 min) em segundo plano
start "Rastreador" python rastreador_b3_continuo.py
