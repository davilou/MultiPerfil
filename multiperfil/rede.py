"""Portas locais: achar uma livre e esperar um processo começar a escutar nela."""

from __future__ import annotations

import socket
import subprocess
import time


class ErroRede(Exception):
    pass


def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def esperar_porta(porta: int, processo: subprocess.Popen, prazo_s: float) -> None:
    """Espera `porta` aceitar conexão; falha na hora se o processo dono morrer.

    Corrida aceita: entre `porta_livre` e o processo ocupar a porta, outro programa
    poderia pegá-la. Numa máquina de um usuário a janela é de milissegundos.
    """
    limite = time.monotonic() + prazo_s
    while time.monotonic() < limite:
        if (codigo := processo.poll()) is not None:
            raise ErroRede(f"processo saiu com código {codigo} antes de escutar na porta {porta}")
        try:
            with socket.create_connection(("127.0.0.1", porta), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise ErroRede(f"porta {porta} não abriu em {prazo_s}s")


def porta_aberta(porta: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", porta), timeout=0.5):
            return True
    except OSError:
        return False


def esperar_porta_fechar(porta: int, prazo_s: float) -> bool:
    limite = time.monotonic() + prazo_s
    while time.monotonic() < limite:
        if not porta_aberta(porta):
            return True
        time.sleep(0.2)
    return False
