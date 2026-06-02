import time
from rastreador_b3 import rodar_rastreador  # ou copie a função para cá

if __name__ == "__main__":
    while True:
        rodar_rastreador()
        print("⏳ Aguardando 15 minutos...")
        time.sleep(900)  # 15 minutos