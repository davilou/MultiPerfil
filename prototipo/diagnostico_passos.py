"""Diagnóstico: em qual passo o navegador trava? Cada passo tem cronômetro e prazo.

Uso: .venv\\Scripts\\python prototipo\\diagnostico_passos.py <variante>
Variantes: base | fuso | sessao | tudo
"""

import asyncio
import json
import sys
import time
from pathlib import Path

from camoufox.geolocation import get_geolocation
from camoufox.ip import public_ip
from playwright.async_api import async_playwright

from multiperfil.lancador import Lancador
from multiperfil.proxy import parse_proxy, testar
from multiperfil.repositorio import Perfil

PASTA = Path("dados/spike")
PRAZO_S = 45
INICIO = time.perf_counter()


def marca(texto: str) -> None:
    print(f"[{time.perf_counter() - INICIO:6.1f}s] {texto}", flush=True)


async def passo(nome: str, corrotina):
    marca(f"{nome}...")
    resultado = await asyncio.wait_for(corrotina, PRAZO_S)
    marca(f"{nome} ok")
    return resultado


def opcoes_contexto(variante: str, fuso: str) -> dict:
    opcoes: dict = {"no_viewport": True}
    if variante in ("fuso", "tudo"):
        opcoes["timezone_id"] = fuso
    if variante in ("sessao", "tudo"):
        opcoes["storage_state"] = str(PASTA / "sessao.json")
    return opcoes


async def main(variante: str) -> None:
    proxy = parse_proxy(Path("dados/proxy.txt").read_text(encoding="utf-8"))
    fuso = testar(proxy, public_ip, get_geolocation).fuso
    marca(f"proxy testado, fuso {fuso}")
    config = json.loads((PASTA / "config.json").read_text())
    perfil, lancador = Perfil("diag", "Diag", "windows", proxy, config, ""), Lancador()
    ws = lancador.abrir(perfil)
    marca("servidor no ar")
    try:
        async with async_playwright() as pw:
            browser = await passo("connect", pw.firefox.connect(ws))
            ctx = await passo("new_context", browser.new_context(**opcoes_contexto(variante, fuso)))
            page = await passo("new_page", ctx.new_page())
            fuso_pagina = await passo("evaluate", page.evaluate(
                "Intl.DateTimeFormat().resolvedOptions().timeZone"))
            marca(f"fuso na página: {fuso_pagina}")
            from spike_login_sonda import SONDA
            await passo("sonda canvas", page.evaluate(SONDA))
            await passo("goto studio", page.goto("https://studio.youtube.com", timeout=PRAZO_S * 1000))
            marca(f"url: {page.url[:60]}")
            await passo("browser.close", browser.close())
    finally:
        marca("fechando servidor")
        lancador.fechar(perfil.id)
        marca("servidor fechado")


asyncio.run(main(sys.argv[1]))
