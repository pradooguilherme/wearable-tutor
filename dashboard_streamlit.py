from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

try:
    import altair as alt
except Exception:  # pragma: no cover - optional dependency
    alt = None

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:  # pragma: no cover - optional dependency
    st_autorefresh = None


def carregar_env_local(caminho_env: Path) -> None:
    if not caminho_env.exists():
        return

    for linha in caminho_env.read_text(encoding="utf-8").splitlines():
        texto = linha.strip()
        if not texto or texto.startswith("#") or "=" not in texto:
            continue

        chave, valor = texto.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip())


BASE_DIR = Path(__file__).resolve().parent
carregar_env_local(BASE_DIR / ".env")

DB_PATH = Path(os.getenv("DB_PATH", str(BASE_DIR / "foco_tracker.db")))
if not DB_PATH.is_absolute():
    DB_PATH = BASE_DIR / DB_PATH

ESP32_IP = os.getenv("ESP32_IP", "192.168.1.5")
MAC_SMARTWATCH = os.getenv("MAC_SMARTWATCH", "55:A2:44:15:22:13")
STREAMLIT_SERVER_PORT = os.getenv("STREAMLIT_SERVER_PORT", "8501")


st.set_page_config(
    page_title="Dashboard de Produtividade",
    page_icon="📈",
    layout="wide",
)


@st.cache_data(ttl=5)
def carregar_dados(db_path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    caminho = Path(db_path)

    if not caminho.exists():
        return pd.DataFrame(), pd.DataFrame()

    with sqlite3.connect(caminho) as conn:
        sessoes = pd.read_sql(
            """
            SELECT id, inicio, fim, tempo_total_focado, concluida_com_sucesso
            FROM sessoes
            ORDER BY datetime(inicio) DESC, id DESC
            """,
            conn,
        )
        logs = pd.read_sql(
            """
            SELECT id, timestamp, rssi, proximidade_extrema
            FROM logs_sinal
            ORDER BY datetime(timestamp) ASC, id ASC
            """,
            conn,
        )

    return sessoes, logs


def formatar_tempo_segundos(segundos: float) -> str:
    total = max(int(segundos), 0)
    horas, resto = divmod(total, 3600)
    minutos, segundos_restantes = divmod(resto, 60)

    partes = []
    if horas:
        partes.append(f"{horas}h")
    if minutos or horas:
        partes.append(f"{minutos}m")
    partes.append(f"{segundos_restantes}s")
    return " ".join(partes)


def preparar_sessoes_exibicao(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    exibicao = df.copy()
    exibicao["inicio"] = pd.to_datetime(exibicao["inicio"], errors="coerce").dt.strftime("%d/%m/%Y %H:%M:%S")
    exibicao["fim"] = pd.to_datetime(exibicao["fim"], errors="coerce").dt.strftime("%d/%m/%Y %H:%M:%S")
    exibicao["tempo_total_focado"] = exibicao["tempo_total_focado"].apply(formatar_tempo_segundos)
    exibicao["concluida_com_sucesso"] = exibicao["concluida_com_sucesso"].map({1: "Sucesso", 0: "Interrompida"})
    exibicao = exibicao.rename(
        columns={
            "inicio": "Início",
            "fim": "Fim",
            "tempo_total_focado": "Tempo Total",
            "concluida_com_sucesso": "Status",
        }
    )
    return exibicao[["Início", "Fim", "Tempo Total", "Status"]]


def resumir_sessoes_do_dia(df: pd.DataFrame) -> tuple[str, int, int]:
    if df.empty:
        return "0s", 0, 0

    dados = df.copy()
    dados["inicio_dt"] = pd.to_datetime(dados["inicio"], errors="coerce")
    dados = dados.dropna(subset=["inicio_dt"])

    hoje = pd.Timestamp.now().normalize()
    dados_hoje = dados[dados["inicio_dt"].dt.normalize() == hoje]

    if dados_hoje.empty:
        return "0s", 0, 0

    total_segundos = float(dados_hoje["tempo_total_focado"].fillna(0).sum())
    sucesso = int((dados_hoje["concluida_com_sucesso"] == 1).sum())
    interrompidas = int((dados_hoje["concluida_com_sucesso"] == 0).sum())
    return formatar_tempo_segundos(total_segundos), sucesso, interrompidas


def selecionar_sessao(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    opcoes = list(df["id"].astype(int).tolist())
    rotulos = {
        int(row.id): f"#{int(row.id)} - {row.inicio}"
        for row in df.itertuples(index=False)
    }

    escolha = st.selectbox(
        "Sessão para visualizar no gráfico de RSSI",
        opcoes,
        format_func=lambda session_id: rotulos.get(int(session_id), f"Sessão {session_id}"),
    )
    return df[df["id"] == escolha]


def preparar_logs_exibicao(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    exibicao = df.copy()
    exibicao["timestamp"] = pd.to_datetime(exibicao["timestamp"], errors="coerce")
    exibicao = exibicao.dropna(subset=["timestamp"])
    exibicao = exibicao.sort_values(["timestamp", "id"])
    return exibicao


def preparar_logs_grafico(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    exibicao = df.copy()
    exibicao = exibicao.sort_values(["timestamp", "id"]).reset_index(drop=True)
    inicio_sessao = exibicao["timestamp"].iloc[0]
    exibicao["minuto_sessao"] = (exibicao["timestamp"] - inicio_sessao).dt.total_seconds() / 60.0
    exibicao["minuto_sessao"] = exibicao["minuto_sessao"].round(2)
    exibicao["hora_formatada"] = exibicao["timestamp"].dt.strftime("%H:%M:%S")
    return exibicao


st.title("Dashboard de Produtividade")
st.caption("Leitura local do SQLite com atualização leve para acompanhar o monitor principal em segundo plano.")

with st.sidebar:
    st.subheader("Configuração ativa")
    st.write(f"Banco de dados: {DB_PATH}")
    st.write(f"ESP32: {ESP32_IP}")
    st.write(f"Smartwatch: {MAC_SMARTWATCH}")
    st.write(f"Porta do Streamlit: {STREAMLIT_SERVER_PORT}")

coluna_controle_1, coluna_controle_2 = st.columns([1, 3])
with coluna_controle_1:
    atualizar = st.button("Atualizar Dados", use_container_width=True)

with coluna_controle_2:
    if st_autorefresh is not None:
        st_autorefresh(interval=5000, key="dashboard_autorefresh")
    else:
        st.info("Se quiser atualização automática, instale `streamlit-autorefresh`. O botão de atualização já está ativo.")

if atualizar:
    st.cache_data.clear()
    st.rerun()

sessoes_df, logs_df = carregar_dados(str(DB_PATH))

if sessoes_df.empty and logs_df.empty:
    st.info("O banco ainda não possui dados. Inicie o monitor principal para começar a coletar sessões e sinais.")
    st.stop()

tempo_total_hoje, sessoes_sucesso, sessoes_interrompidas = resumir_sessoes_do_dia(sessoes_df)

col1, col2, col3 = st.columns(3)
col1.metric("Tempo total focado hoje", tempo_total_hoje)
col2.metric("Sessões concluídas com sucesso", sessoes_sucesso)
col3.metric("Sessões interrompidas", sessoes_interrompidas)

st.divider()
st.subheader("Estabilidade do sinal")

if sessoes_df.empty:
    st.info("Ainda não há sessões para exibir no gráfico de sinal.")
else:
    sessoes_ordenadas = sessoes_df.copy()
    sessoes_ordenadas["inicio_dt"] = pd.to_datetime(sessoes_ordenadas["inicio"], errors="coerce")
    sessoes_ordenadas = sessoes_ordenadas.dropna(subset=["inicio_dt"])
    sessoes_ordenadas = sessoes_ordenadas.sort_values(["inicio_dt", "id"], ascending=[False, False])

    sessao_escolhida_df = selecionar_sessao(sessoes_ordenadas)

    if sessao_escolhida_df.empty:
        st.info("Não foi possível localizar a sessão selecionada.")
    else:
        sessao_id = int(sessao_escolhida_df.iloc[0]["id"])
        sessao_logs = preparar_logs_exibicao(logs_df)

        if sessao_logs.empty:
            st.info("Não há amostras de RSSI registradas para esta sessão.")
        else:
            inicio_sessao = pd.to_datetime(sessao_escolhida_df.iloc[0]["inicio"], errors="coerce")
            fim_sessao = pd.to_datetime(sessao_escolhida_df.iloc[0]["fim"], errors="coerce")

            if pd.isna(inicio_sessao) or pd.isna(fim_sessao):
                sessao_logs_filtrados = sessao_logs
            else:
                sessao_logs_filtrados = sessao_logs[
                    (sessao_logs["timestamp"] >= inicio_sessao) & (sessao_logs["timestamp"] <= fim_sessao)
                ]

            if sessao_logs_filtrados.empty:
                st.info("A sessão selecionada ainda não possui logs no intervalo correspondente.")
            else:
                grafico_df = preparar_logs_grafico(sessao_logs_filtrados)
                pontos_proximidade = grafico_df[grafico_df["proximidade_extrema"] == 1]

                if alt is not None:
                    base = alt.Chart(grafico_df).encode(
                        x=alt.X("minuto_sessao:Q", title="Minutos"),
                        y=alt.Y("rssi:Q", title="RSSI (dBm)"),
                        tooltip=[
                            alt.Tooltip("hora_formatada:N", title="Horário"),
                            alt.Tooltip("minuto_sessao:Q", title="Minuto da sessão"),
                            alt.Tooltip("rssi:Q", title="RSSI"),
                            alt.Tooltip("proximidade_extrema:N", title="Proximidade extrema"),
                        ],
                    )
                    linha = base.mark_line(color="#1f77b4", strokeWidth=2)
                    pontos = (
                        alt.Chart(pontos_proximidade)
                        .mark_circle(size=110, color="#d62728")
                        .encode(x="minuto_sessao:Q", y="rssi:Q")
                    )
                    st.altair_chart((linha + pontos).properties(height=320), use_container_width=True)
                else:
                    st.line_chart(grafico_df.set_index("minuto_sessao")["rssi"], height=300)
                    if not pontos_proximidade.empty:
                        st.write("Momentos de proximidade extrema")
                        st.scatter_chart(pontos_proximidade.set_index("minuto_sessao")["rssi"], height=180)

                st.caption(f"Sessão exibida: #{sessao_id}")

st.divider()
st.subheader("Histórico de sessões")

historico_exibicao = preparar_sessoes_exibicao(sessoes_df)
if historico_exibicao.empty:
    st.info("Ainda não há sessões registradas no banco.")
else:
    st.dataframe(historico_exibicao, use_container_width=True, hide_index=True)
