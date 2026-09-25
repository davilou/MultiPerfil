"""Sobe um Camoufox por perfil como servidor Playwright e devolve o ws://.

Reproduz camoufox.server.launch_server (0.5.6), com uma diferença: o config sorteado
por launch_options é trocado pelo congelado do perfil (ver fingerprint.py).
"""

from __future__ import annotations

import base64
import logging
import queue
import re
import subprocess
import threading
import time
from pathlib import Path

import orjson
from camoufox.server import LAUNCH_SCRIPT, get_nodejs, to_camel_case_dict
from camoufox.utils import launch_options

from multiperfil.fingerprint import aplicar_congelado
from multiperfil.proxy import para_playwright
from multiperfil.repositorio import Perfil

log = logging.getLogger("multiperfil.lancador")

PADRAO_WS = re.compile(r"ws://\S+")
ANSI = re.compile(r"\x1b\[[0-9;]*m")
PRAZO_ABRIR_S = 90
PRAZO_FECHAR_S = 15


class ErroLancamento(Exception):
    pass


def achar_endpoint(linha: str) -> str | None:
    achado = PADRAO_WS.search(ANSI.sub("", linha))
    return achado.group(0) if achado else None


def _opcoes(perfil: Perfil) -> dict:
    opcoes = launch_options(
        config=dict(perfil.config),
        headless=False,
        geoip=True,
        proxy=para_playwright(perfil.proxy),
        firefox_user_prefs={"network.proxy.socks_remote_dns": True},
        i_know_what_im_doing=True,
    )
    return aplicar_congelado(opcoes, perfil.config)


def _drenar(processo: subprocess.Popen, linhas: queue.Queue, perfil_id: str) -> None:
    assert processo.stdout is not None
    for linha in processo.stdout:
        linhas.put(linha)
        log.info("[%s] %s", perfil_id, ANSI.sub("", linha).rstrip())
    linhas.put(None)


def _esperar_endpoint(linhas: queue.Queue, perfil_id: str) -> str:
    limite = time.monotonic() + PRAZO_ABRIR_S
    while (restante := limite - time.monotonic()) > 0:
        try:
            linha = linhas.get(timeout=restante)
        except queue.Empty:
            break
        if linha is None:
            raise ErroLancamento(f"navegador do perfil {perfil_id} saiu antes de abrir")
        if ws := achar_endpoint(linha):
            return ws
    raise ErroLancamento(f"perfil {perfil_id} não abriu em {PRAZO_ABRIR_S}s")


class Lancador:
    def __init__(self) -> None:
        self._processos: dict[str, subprocess.Popen] = {}

    def abrir(self, perfil: Perfil) -> str:
        dados = orjson.dumps(to_camel_case_dict(_opcoes(perfil)))
        node = get_nodejs()
        pacote = Path(node).parent / "package"
        processo = subprocess.Popen(  # nosec - comando fixo, sem shell
            [node, str(LAUNCH_SCRIPT), str(pacote)],
            cwd=pacote, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8",
        )
        assert processo.stdin is not None
        processo.stdin.write(base64.b64encode(dados).decode() + "\n")
        processo.stdin.flush()
        linhas: queue.Queue = queue.Queue()
        threading.Thread(target=_drenar, args=(processo, linhas, perfil.id), daemon=True).start()
        self._processos[perfil.id] = processo
        try:
            return _esperar_endpoint(linhas, perfil.id)
        except ErroLancamento:
            self.fechar(perfil.id)
            raise

    def vivo(self, perfil_id: str) -> bool:
        processo = self._processos.get(perfil_id)
        return processo is not None and processo.poll() is None

    def fechar(self, perfil_id: str) -> None:
        """Fechar o stdin pede ao Node que feche o navegador limpo; depois, força."""
        processo = self._processos.pop(perfil_id, None)
        if processo is None:
            return
        assert processo.stdin is not None
        if not processo.stdin.closed:
            processo.stdin.close()
        try:
            processo.wait(timeout=PRAZO_FECHAR_S)
        except subprocess.TimeoutExpired:
            log.warning("[%s] não fechou em %ss, encerrando à força", perfil_id, PRAZO_FECHAR_S)
            processo.kill()
            processo.wait()
