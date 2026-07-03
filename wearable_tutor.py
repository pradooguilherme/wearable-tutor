import asyncio
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from bleak import BleakScanner
import aiohttp

from foco_db import registrar_log_sinal, registrar_sessao


@dataclass(frozen=True)
class Configuracao:
    mac_smartwatch: str
    esp32_ip: str
    limiar_rssi: int
    tolerancia_ausencia: int
    intervalo_varredura: float
    tempo_limite_pomodoro: int
    tempo_espera_proximo_ciclo: int
    limiar_proximidade_extrema: int
    tempo_bonus_extensao: int


@dataclass
class EstadoMonitoramento:
    sessao_ativa: bool = False
    falhas_consecutivas: int = 0
    tempo_total_estudo: float = 0.0
    tempo_ultima_leitura: float = 0.0
    tempo_limite_dinamico: int = 0
    inicio_sessao_str: str | None = None


def carregar_env_local(caminho_env: Path) -> None:
    if not caminho_env.exists():
        return

    for linha in caminho_env.read_text(encoding="utf-8").splitlines():
        texto = linha.strip()
        if not texto or texto.startswith("#") or "=" not in texto:
            continue

        chave, valor = texto.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip())


def carregar_configuracao() -> Configuracao:
    base_dir = Path(__file__).resolve().parent
    carregar_env_local(base_dir / ".env")

    return Configuracao(
        mac_smartwatch=os.getenv("MAC_SMARTWATCH", "55:A2:44:15:22:13"),
        esp32_ip=os.getenv("ESP32_IP", "192.168.1.5"),
        limiar_rssi=int(os.getenv("LIMIAR_RSSI", "-150")),
        tolerancia_ausencia=int(os.getenv("TOLERANCIA_AUSENCIA", "4")),
        intervalo_varredura=float(os.getenv("INTERVALO_VARREDURA", "0.5")),
        tempo_limite_pomodoro=int(os.getenv("TEMPO_LIMITE_POMODORO", "20")),
        tempo_espera_proximo_ciclo=int(os.getenv("TEMPO_ESPERA_PROXIMO_CICLO", "15")),
        limiar_proximidade_extrema=int(os.getenv("LIMIAR_PROXIMIDADE_EXTREMA", "-35")),
        tempo_bonus_extensao=int(os.getenv("TEMPO_BONUS_EXTENSAO", "10")),
    )


async def enviar_vibracao_led(configuracao: Configuracao, nivel_alerta):
    rota = "/leve" if nivel_alerta == 1 else "/forte"
    url = f"http://{configuracao.esp32_ip}{rota}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=2.0) as response:
                if response.status == 200:
                    pass
    except Exception as e:
        print(f"\n[ESP32 ERRO] Não foi possível comunicar com o LED: {e}")

async def verificar_presenca_imediata(configuracao: Configuracao):
    """Função auxiliar para checar rapidamente se o relógio está presente agora"""
    dispositivos = await BleakScanner.discover(timeout=5.0, return_adv=True)
    for endereco, (device, adv_data) in dispositivos.items():
        if endereco.upper() == configuracao.mac_smartwatch.upper() and adv_data.rssi >= configuracao.limiar_rssi:
            return True, adv_data.rssi
    return False, None

async def aguardar_proximo_ciclo(configuracao: Configuracao):
    """Roda durante o minuto de transição após o Pomodoro acabar"""
    print(f"\n[AGUARDANDO] Pomodoro finalizado. Iniciando intervalo de {configuracao.tempo_espera_proximo_ciclo}s...")
    print("[AGUARDANDO] Se você sair da mesa, o sistema voltará para a busca geral.")
    
    tempo_inicio_pausa = time.time()
    falhas_pausa = 0

    while (time.time() - tempo_inicio_pausa) < configuracao.tempo_espera_proximo_ciclo:
        presente, rssi = await verificar_presenca_imediata(configuracao)
        
        if not presente:
            falhas_pausa += 1
            print(f"    [-] Sinal perdido durante intervalo... ({falhas_pausa}/{configuracao.tolerancia_ausencia})    ", end="\r")
            if falhas_pausa >= configuracao.tolerancia_ausencia:
                print("\n[-] Usuário saiu da mesa durante o intervalo! Cancelando próximo ciclo.")
                return False
        else:
            falhas_pausa = 0
            tempo_restante = max(0, int(configuracao.tempo_espera_proximo_ciclo - (time.time() - tempo_inicio_pausa)))
            print(f"    Usuário presente ({rssi} dBm) | Próximo ciclo em: {tempo_restante}s    ", end="\r")

        await asyncio.sleep(configuracao.intervalo_varredura)
        
    print("\n[+] Usuário permaneceu na mesa! Reiniciando um novo ciclo automaticamente...")
    return True

async def escanear_e_avaliar(configuracao: Configuracao):
    estado = EstadoMonitoramento(tempo_limite_dinamico=configuracao.tempo_limite_pomodoro)
   
    print("\n[SISTEMA] Iniciando monitoramento de presença...")
    print(f"[SISTEMA] Procurando pelo Smartwatch: {configuracao.mac_smartwatch}\n")
   
    while True:
        dispositivos = await BleakScanner.discover(timeout=5.0, return_adv=True)
        relogio_encontrado = False
        rssi_atual = None
       
        if not estado.sessao_ativa:
            print(f"\n--- Foram encontrados {len(dispositivos)} dispositivos nesta varredura ---")
       
        for endereco, (device, adv_data) in dispositivos.items():
            if endereco.upper() == configuracao.mac_smartwatch.upper():
                relogio_encontrado = True
                rssi_atual = adv_data.rssi
               
            if not estado.sessao_ativa:
                hora_atual = datetime.now().strftime("%H:%M:%S")
                nome = adv_data.local_name or device.name or "Desconhecido"
                print(f"[SCAN | {hora_atual}] MAC: {endereco} | Nome: {nome} | RSSI: {adv_data.rssi} dBm")
               
        # ==========================================
        # MÁQUINA DE ESTADOS PRINCIPAL
        # ==========================================
        if relogio_encontrado and rssi_atual >= configuracao.limiar_rssi:
            estado.falhas_consecutivas = 0
            agora = time.time()
           
            if not estado.sessao_ativa:
                estado.sessao_ativa = True
                estado.inicio_sessao_str = datetime.now().isoformat()
                estado.tempo_total_estudo = 0.0
                estado.tempo_limite_dinamico = configuracao.tempo_limite_pomodoro  # Reseta o limite para o padrão
                estado.tempo_ultima_leitura = agora
                print(f"\n[+] Usuário detectado ({rssi_atual} dBm). SESSÃO INICIADA!")
                asyncio.create_task(enviar_vibracao_led(configuracao, 1))
            else:
                registrar_log_sinal(rssi_atual, proximidade_extrema=False)
                estado.tempo_total_estudo += (agora - estado.tempo_ultima_leitura)
                estado.tempo_ultima_leitura = agora
                
                # --- IMPLEMENTAÇÃO DA IDEIA 2 (DETECÇÃO DE PROXIMIDADE) ---
                if rssi_atual >= configuracao.limiar_proximidade_extrema:
                    registrar_log_sinal(rssi_atual, proximidade_extrema=True)
                    estado.tempo_limite_dinamico += configuracao.tempo_bonus_extensao
                    print(f"\n[GESTO] Proximidade extrema detectada ({rssi_atual} dBm)!")
                    print(f"[GESTO] +{configuracao.tempo_bonus_extensao}s adicionados. Novo limite: {estado.tempo_limite_dinamico}s")
                    # Sinaliza com uma piscada leve que o tempo foi adicionado
                    asyncio.create_task(enviar_vibracao_led(configuracao, 1))
                
                # Exibe o progresso baseado no limite dinâmico atualizado
                print(f"    Sinal OK ({rssi_atual} dBm) | Tempo: {int(estado.tempo_total_estudo)}s / {estado.tempo_limite_dinamico}s     ", end="\r")
                
                # SE O TEMPO DO POMODORO ACABAR (Usando o limite dinâmico):
                if estado.tempo_total_estudo >= estado.tempo_limite_dinamico:
                    print("\n>>> [POMODORO] Tempo de foco concluído! <<<")
                    # Pisca 5 vezes (Forte) indicando fim do tempo
                    await enviar_vibracao_led(configuracao, 2) 
                    instante_fim = datetime.now().isoformat()
                    registrar_sessao(
                        estado.inicio_sessao_str,
                        instante_fim,
                        estado.tempo_total_estudo,
                        True,
                    )
                    
                    # Entra na função de espera inteligente de 1 minuto
                    deve_recomencar = await aguardar_proximo_ciclo(configuracao)
                    
                    if deve_recomencar:
                        # Reseta as variáveis para começar um ciclo do zero imediatamente
                        estado.tempo_total_estudo = 0.0
                        estado.tempo_limite_dinamico = configuracao.tempo_limite_pomodoro
                        estado.tempo_ultima_leitura = time.time()
                        estado.falhas_consecutivas = 0
                        estado.inicio_sessao_str = datetime.now().isoformat()
                        # Pisca leve indicando o começo do novo ciclo
                        asyncio.create_task(enviar_vibracao_led(configuracao, 1)) 
                    else:
                        # Se ele saiu, desativa a sessão e o loop principal voltará a buscar aparelhos
                        estado.sessao_ativa = False
                        estado.inicio_sessao_str = None
                        asyncio.create_task(enviar_vibracao_led(configuracao, 1)) # Pisca saída
               
        else:
            if estado.sessao_ativa:
                estado.falhas_consecutivas += 1
                agora = time.time()
                estado.tempo_ultima_leitura = agora
               
                print(f"\n[!] Avaliando saída... {rssi_atual} Cronômetro pausado em {int(estado.tempo_total_estudo)}s. ({estado.falhas_consecutivas}/{configuracao.tolerancia_ausencia})")
               
                if estado.falhas_consecutivas >= configuracao.tolerancia_ausencia:
                    instante_fim = datetime.now().isoformat()
                    registrar_sessao(
                        estado.inicio_sessao_str,
                        instante_fim,
                        estado.tempo_total_estudo,
                        False,
                    )
                    estado.sessao_ativa = False
                    estado.inicio_sessao_str = None
                    print(f"\n[-] Usuário ausente. SESSÃO ENCERRADA. Tempo focado: {int(estado.tempo_total_estudo)}s\n")
                    asyncio.create_task(enviar_vibracao_led(configuracao, 1))

        await asyncio.sleep(configuracao.intervalo_varredura)

if __name__ == "__main__":
    try:
        asyncio.run(escanear_e_avaliar(carregar_configuracao()))
    except KeyboardInterrupt:
        print("\n\n[SISTEMA] Monitoramento encerrado pelo usuário.")