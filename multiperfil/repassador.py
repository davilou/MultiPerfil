"""Proxy local sem senha na frente do proxy real: o Chromium não aceita proxy com senha.

Usa pproxy. A credencial vai num arquivo que o pproxy lê (`##arquivo`), nunca na linha
de comando — que qualquer processo da máquina consegue listar. O arquivo some ao fechar.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from multiperfil.proxy import Proxy
from multiperfil.rede import esperar_porta, porta_livre

PRAZO_S = 10
ESQUEMA_PPROXY = {"http": "http", "https": "http+ssl", "socks5": "socks5"}


def uri_remota(proxy: Proxy, arquivo_auth: Path | None) -> str:
    base = f"{ESQUEMA_PPROXY[proxy.esquema]}://{proxy.host}:{proxy.porta}"
    return f"{base}##{arquivo_auth}" if arquivo_auth else base


class Repassador:
    """Um pproxy por perfil aberto. Chamador serializa por perfil_id (estado.Registro)."""

    def __init__(self, pasta: Path) -> None:
        self._pasta = pasta
        self._processos: dict[str, subprocess.Popen] = {}
        # Credencial que sobrou de uma queda do serviço: no início nenhum repassador
        # desta instância existe, então todo .auth na pasta é lixo com senha dentro.
        for sobra in pasta.glob("*.auth"):
            sobra.unlink()

    def _escrever_auth(self, perfil_id: str, proxy: Proxy) -> Path | None:
        if not proxy.usuario:
            return None
        self._pasta.mkdir(parents=True, exist_ok=True)
        arquivo = self._pasta / f"{perfil_id}.auth"
        arquivo.write_text(f"{proxy.usuario}:{proxy.senha or ''}", encoding="utf-8")
        return arquivo

    def abrir(self, perfil_id: str, proxy: Proxy) -> int:
        self.fechar(perfil_id)
        porta = porta_livre()
        remoto = uri_remota(proxy, self._escrever_auth(perfil_id, proxy))
        processo = subprocess.Popen(  # nosec - argv fixo, sem shell
            [sys.executable, "-m", "pproxy", "-l", f"http://127.0.0.1:{porta}", "-r", remoto],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        self._processos[perfil_id] = processo
        try:
            esperar_porta(porta, processo, PRAZO_S)
        except Exception:
            self.fechar(perfil_id)
            raise
        return porta

    def fechar(self, perfil_id: str) -> None:
        processo = self._processos.pop(perfil_id, None)
        if processo is not None:
            processo.kill()
            processo.wait()
        (self._pasta / f"{perfil_id}.auth").unlink(missing_ok=True)
