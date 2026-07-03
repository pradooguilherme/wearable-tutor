import atexit
import queue
import sqlite3
import threading
from datetime import datetime
from pathlib import Path


DB_PATH = Path(__file__).resolve().with_name("foco_tracker.db")

_job_queue: queue.Queue = queue.Queue()
_worker_ready = threading.Event()
_worker_started = False
_worker_lock = threading.Lock()


def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def _criar_tabelas(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS logs_sinal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            rssi INTEGER NOT NULL,
            proximidade_extrema INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inicio TEXT NOT NULL,
            fim TEXT NOT NULL,
            tempo_total_focado REAL NOT NULL,
            concluida_com_sucesso INTEGER NOT NULL
        )
        """
    )
    conn.commit()


def _registrar_log_sinal(conn, timestamp, rssi, proximidade_extrema):
    conn.execute(
        """
        INSERT INTO logs_sinal (timestamp, rssi, proximidade_extrema)
        VALUES (?, ?, ?)
        """,
        (timestamp, rssi, 1 if proximidade_extrema else 0),
    )
    conn.commit()


def _registrar_sessao(conn, inicio, fim, tempo_total_focado, concluida_com_sucesso):
    conn.execute(
        """
        INSERT INTO sessoes (inicio, fim, tempo_total_focado, concluida_com_sucesso)
        VALUES (?, ?, ?, ?)
        """,
        (inicio, fim, float(tempo_total_focado), 1 if concluida_com_sucesso else 0),
    )
    conn.commit()


def _worker():
    conn = _connect()
    try:
        _criar_tabelas(conn)
        _worker_ready.set()

        while True:
            job = _job_queue.get()
            if job is None:
                _job_queue.task_done()
                break

            action, payload = job
            try:
                if action == "log_sinal":
                    _registrar_log_sinal(conn, *payload)
                elif action == "sessao":
                    _registrar_sessao(conn, *payload)
            except Exception as exc:
                print(f"[DB ERRO] Falha ao persistir dados: {exc}")
            finally:
                _job_queue.task_done()
    finally:
        conn.close()


def inicializar_banco():
    global _worker_started

    with _worker_lock:
        if _worker_started:
            return

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        _worker_started = True


def registrar_log_sinal(rssi, proximidade_extrema=False, timestamp=None):
    if timestamp is None:
        timestamp = datetime.now().isoformat(timespec="seconds")

    inicializar_banco()
    _job_queue.put(("log_sinal", (timestamp, int(rssi), bool(proximidade_extrema))))


def registrar_sessao(inicio, fim, tempo_total_focado, concluida_com_sucesso):
    inicializar_banco()
    _job_queue.put(
        (
            "sessao",
            (
                inicio,
                fim,
                tempo_total_focado,
                bool(concluida_com_sucesso),
            ),
        )
    )


def encerrar_banco():
    if not _worker_started:
        return

    _job_queue.put(None)


inicializar_banco()
atexit.register(encerrar_banco)