"""Sobe um Camoufox por perfil como servidor Playwright e devolve o ws://.

Reproduz camoufox.server.launch_server (0.5.6), com uma diferença: o config sorteado
por launch_options é trocado pelo congelado do perfil (ver fingerprint.py).
"""

from __future__ import annotations

import base64
import logging
import os
import queue
import re
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import quote

import orjson
from camoufox.server import LAUNCH_SCRIPT, get_nodejs, to_camel_case_dict
from camoufox.utils import launch_options

from multiperfil.fingerprint import aplicar_congelado
from multiperfil.proxy import Proxy, para_playwright
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


def limpar_linha(linha: str, segredos: tuple[str, ...]) -> str:
    """Tira códigos ANSI e mascara cada segredo não vazio antes de ir pro log."""
    texto = ANSI.sub("", linha)
    for segredo in segredos:
        if segredo:
            texto = texto.replace(segredo, "***")
    return texto


def comando_matar_arvore(pid: int, sistema: str) -> list[str] | None:
    """Comando para matar o processo e seus filhos. None = kill() já basta."""
    if sistema == "nt":
        return ["taskkill", "/pid", str(pid), "/T", "/F"]
    return None


def _segredos(proxy: Proxy) -> tuple[str, ...]:
    if not proxy.senha:
        return ()
    return (proxy.senha, quote(proxy.senha, safe=""))


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


def _drenar(
    processo: subprocess.Popen,
    linhas: queue.Queue,
    perfil_id: str,
    pronto: threading.Event,
    segredos: tuple[str, ...],
) -> None:
    """Lê o stdout até o fim; só enfileira enquanto ninguém achou o endpoint ainda."""
    assert processo.stdout is not None
    for linha in processo.stdout:
        if not pronto.is_set():
            linhas.put(linha)
        log.info("[%s] %s", perfil_id, limpar_linha(linha, segredos).rstrip())
    if not pronto.is_set():
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


def _escrever_config(processo: subprocess.Popen, dados: bytes, perfil_id: str) -> None:
    assert processo.stdin is not None
    try:
        processo.stdin.write(base64.b64encode(dados).decode() + "\n")
        processo.stdin.flush()
    except OSError as erro:
        raise ErroLancamento(
            f"navegador do perfil {perfil_id} saiu antes de receber a configuração"
        ) from erro


def _matar_forcado(processo: subprocess.Popen) -> None:
    comando = comando_matar_arvore(processo.pid, os.name)
    if comando is None:
        processo.kill()
    else:
        subprocess.run(comando, check=False, capture_output=True)
    processo.wait()


class Lancador:
    """Sobe/fecha um navegador por perfil. O chamador serializa as chamadas por
    perfil_id (a API faz isso via estado.Registro) — esta classe não trava sozinha.
    """

    def __init__(self) -> None:
        self._processos: dict[str, subprocess.Popen] = {}

    def abrir(self, perfil: Perfil) -> str:
        dados = orjson.dumps(to_camel_case_dict(_opcoes(perfil)))
        node = get_nodejs()
        pacote = Path(node).parent / "package"
        processo = subprocess.Popen(  # nosec - comando fixo, sem shell
            [node, str(LAUNCH_SCRIPT), str(pacote)],
            cwd=pacote, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
        )
        self._processos[perfil.id] = processo
        pronto = threading.Event()
        try:
            _escrever_config(processo, dados, perfil.id)
            linhas: queue.Queue = queue.Queue()
            args = (processo, linhas, perfil.id, pronto, _segredos(perfil.proxy))
            threading.Thread(target=_drenar, args=args, daemon=True).start()
            return _esperar_endpoint(linhas, perfil.id)
        except Exception:
            self.fechar(perfil.id)
            raise
        finally:
            pronto.set()

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
            try:
                processo.stdin.close()
            except OSError as erro:
                # Node já morreu com config no buffer; o close tenta o flush e quebra.
                # Relançar esconderia o erro original de abrir(). O wait abaixo reapa.
                log.info("[%s] stdin já estava quebrado ao fechar: %s", perfil_id, erro)
        try:
            processo.wait(timeout=PRAZO_FECHAR_S)
        except subprocess.TimeoutExpired:
            log.warning("[%s] não fechou em %ss, encerrando à força", perfil_id, PRAZO_FECHAR_S)
            _matar_forcado(processo)
