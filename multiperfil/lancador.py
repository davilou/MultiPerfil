"""Sobe e fecha um fingerprint-chromium por perfil e devolve o endereço CDP.

Pasta de perfil persistente (login e cache ficam entre aberturas), seed fixa por perfil,
fuso do IP do proxy, e o proxy entra pelo repassador local (Chromium não aceita senha).
Perfil sem proxy sai pelo IP real, com o fuso do Windows.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Protocol

from playwright.sync_api import Error as ErroPlaywright
from playwright.sync_api import sync_playwright

from multiperfil.proxy import Proxy
from multiperfil.rede import ErroRede, esperar_porta, esperar_porta_fechar, porta_aberta, porta_livre
from multiperfil.repositorio import Perfil

log = logging.getLogger("multiperfil.lancador")

PRAZO_ABRIR_S = 30
PRAZO_FECHAR_S = 15
# Endereço CDP gravado na pasta do perfil enquanto o app o mantém aberto: se o app cair
# (ou for fechado sem fechar o perfil), a próxima abertura acha e fecha o órfão.
# O Chrome não grava DevToolsActivePort com porta fixa (medido em 2026-10-02).
ARQUIVO_CDP = "multiperfil-cdp.txt"


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
        "--restore-last-session",  # reabre as abas de quando o perfil foi fechado
    ]
    if fuso is not None:
        args.append(f"--timezone={fuso}")
    if porta_proxy is not None:
        args.append(f"--proxy-server=http://127.0.0.1:{porta_proxy}")
    return args


def _atualizar_json(arquivo: Path, mudar) -> None:
    dados = json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.exists() else {}
    mudar(dados)
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")


def gravar_nome_no_chrome(pasta_perfil: Path, nome: str) -> None:
    """O nome do MultiPerfil vira o nome do perfil do Chrome (botão e menu de perfil).

    Só com o navegador fechado — o Chrome reescreve esses arquivos enquanto roda.
    O título da janela não muda: o Chrome só põe o nome do perfil nele quando a mesma
    pasta tem vários perfis (medido em 2026-10-02; `--window-name` também não muda).
    """
    def no_estado(dados: dict) -> None:
        cache = dados.setdefault("profile", {}).setdefault("info_cache", {}).setdefault("Default", {})
        cache.update(name=nome, is_using_default_name=False)

    _atualizar_json(pasta_perfil / "Local State", no_estado)
    _atualizar_json(pasta_perfil / "Default" / "Preferences",
                    lambda dados: dados.setdefault("profile", {}).update(name=nome))


def fechar_orfao(pasta_perfil: Path) -> None:
    """Chromium de outra sessão do app segura a pasta do perfil: um 2º Chrome na mesma
    pasta entrega o pedido a ele e sai com código 0 (medido). Fecha limpo — as abas
    ficam salvas — antes de abrir de novo. Marca de porta morta é só apagada."""
    marca = pasta_perfil / ARQUIVO_CDP
    if not marca.exists():
        return
    url = marca.read_text(encoding="utf-8").strip()
    porta = int(url.rsplit(":", 1)[1])
    if porta_aberta(porta):
        log.warning("[%s] navegador órfão de outra sessão; fechando", pasta_perfil.name)
        _pedir_fechamento(url)
        if not esperar_porta_fechar(porta, PRAZO_FECHAR_S):
            raise ErroLancamento(f"o navegador antigo do perfil {pasta_perfil.name} não fechou; "
                                 "feche a janela dele e tente de novo")
    marca.unlink()


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
        pasta = self._pasta_perfis / perfil.id
        fechar_orfao(pasta)  # antes de mexer nos arquivos: o Chrome reescreve enquanto roda
        gravar_nome_no_chrome(pasta, perfil.nome)  # antes do repassador, que precisaria fechar
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
        except ErroRede as erro:
            codigo = processo.poll()
            self.fechar(perfil.id)
            if codigo == 0:  # um Chrome que não é deste app já usa a pasta do perfil
                raise ErroLancamento("outra janela deste perfil já está aberta fora do "
                                     "MultiPerfil; feche-a e tente de novo") from erro
            raise
        except Exception:
            self.fechar(perfil.id)
            raise
        (pasta / ARQUIVO_CDP).write_text(url, encoding="utf-8")
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
            (self._pasta_perfis / perfil_id / ARQUIVO_CDP).unlink(missing_ok=True)

    def _fechar_processo(self, perfil_id: str, processo: subprocess.Popen, url: str) -> None:
        try:
            _pedir_fechamento(url)
            processo.wait(timeout=PRAZO_FECHAR_S)
        except (ErroPlaywright, subprocess.TimeoutExpired) as erro:
            log.warning("[%s] não fechou limpo (%s), encerrando à força", perfil_id, erro)
            _matar_forcado(processo)
