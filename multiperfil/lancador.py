"""Sobe e fecha um fingerprint-chromium por perfil e devolve o endereço CDP.

Pasta de perfil persistente (login e cache ficam entre aberturas), seed fixa por perfil,
fuso do IP do proxy, e o proxy entra pelo repassador local (Chromium não aceita senha).
Perfil sem proxy sai pelo IP real, com o fuso do Windows.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Protocol

from playwright.sync_api import Error as ErroPlaywright
from playwright.sync_api import sync_playwright

from multiperfil.proxy import Proxy
from multiperfil.rede import esperar_porta, porta_livre
from multiperfil.repositorio import Perfil

log = logging.getLogger("multiperfil.lancador")

PRAZO_ABRIR_S = 30
PRAZO_FECHAR_S = 15


class ErroLancamento(Exception):
    pass


class RepassadorProto(Protocol):
    def abrir(self, perfil_id: str, proxy: Proxy) -> int: ...
    def fechar(self, perfil_id: str) -> None: ...


def argumentos_chrome(executavel: Path, pasta_perfil: Path, perfil: Perfil, fuso: str | None,
                      porta_proxy: int | None, porta_cdp: int) -> list[str]:
    """Sem proxy (porta_proxy None) sai pelo IP real; sem fuso, fica o do Windows,
    que é o coerente com o IP real."""
    base = perfil.idioma.split("-")[0]
    aceitos = f"{perfil.idioma},{base}" if "-" in perfil.idioma else perfil.idioma
    args = [
        str(executavel),
        f"--user-data-dir={pasta_perfil}",
        f"--fingerprint={perfil.seed}",
        f"--fingerprint-platform={perfil.sistema}",
        f"--lang={perfil.idioma}",
        f"--accept-lang={aceitos}",
        f"--remote-debugging-port={porta_cdp}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if fuso is not None:
        args.append(f"--timezone={fuso}")
    if porta_proxy is not None:
        args.append(f"--proxy-server=http://127.0.0.1:{porta_proxy}")
    return args


def comando_matar_arvore(pid: int, sistema: str) -> list[str] | None:
    """No Windows matar o pai não mata os filhos; taskkill /T derruba a árvore."""
    return ["taskkill", "/pid", str(pid), "/T", "/F"] if sistema == "nt" else None


def _matar_forcado(processo: subprocess.Popen) -> None:
    comando = comando_matar_arvore(processo.pid, os.name)
    if comando is None:
        processo.kill()
    else:
        subprocess.run(comando, check=False, capture_output=True)
    processo.wait()


def _pedir_fechamento(url_cdp: str) -> None:
    """Browser.close pelo CDP: o Chromium grava cookies e cache antes de sair.

    Encerra o navegador para todos — um script externo ainda conectado perde a conexão.
    Usa a API síncrona do Playwright: só pode ser chamado fora de um loop asyncio (as
    rotas `def` do FastAPI rodam no threadpool, sem loop). Não mover para `async def`.
    """
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(url_cdp, timeout=5000)
        browser.new_browser_cdp_session().send("Browser.close")


class Lancador:
    """Um Chromium por perfil. O chamador serializa por perfil_id (estado.Registro)."""

    def __init__(self, executavel: Path, pasta_perfis: Path, repassador: RepassadorProto) -> None:
        self._executavel = executavel
        self._pasta_perfis = pasta_perfis
        self._repassador = repassador
        self._abertos: dict[str, tuple[subprocess.Popen, str]] = {}

    def abrir(self, perfil: Perfil, fuso: str | None) -> str:
        if not self._executavel.exists():
            raise ErroLancamento(f"navegador não encontrado em {self._executavel}")
        porta_proxy = (self._repassador.abrir(perfil.id, perfil.proxy)
                       if perfil.proxy is not None else None)
        porta_cdp = porta_livre()
        args = argumentos_chrome(self._executavel, self._pasta_perfis / perfil.id, perfil,
                                 fuso, porta_proxy, porta_cdp)
        try:
            processo = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            self._repassador.fechar(perfil.id)
            raise
        url = f"http://127.0.0.1:{porta_cdp}"
        self._abertos[perfil.id] = (processo, url)
        try:
            esperar_porta(porta_cdp, processo, PRAZO_ABRIR_S)
        except Exception:
            self.fechar(perfil.id)
            raise
        return url

    def vivo(self, perfil_id: str) -> bool:
        aberto = self._abertos.get(perfil_id)
        return aberto is not None and aberto[0].poll() is None

    def codigo_saida(self, perfil_id: str) -> int | None:
        """None = rodando ou desconhecido."""
        aberto = self._abertos.get(perfil_id)
        return aberto[0].poll() if aberto else None

    def fechar(self, perfil_id: str) -> None:
        aberto = self._abertos.pop(perfil_id, None)
        try:
            if aberto is not None and aberto[0].poll() is None:
                self._fechar_processo(perfil_id, *aberto)
        finally:
            self._repassador.fechar(perfil_id)

    def _fechar_processo(self, perfil_id: str, processo: subprocess.Popen, url: str) -> None:
        try:
            _pedir_fechamento(url)
            processo.wait(timeout=PRAZO_FECHAR_S)
        except (ErroPlaywright, subprocess.TimeoutExpired) as erro:
            log.warning("[%s] não fechou limpo (%s), encerrando à força", perfil_id, erro)
            _matar_forcado(processo)
