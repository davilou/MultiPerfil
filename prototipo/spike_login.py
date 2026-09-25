"""Spike: o login Google sobrevive entre aberturas e o fingerprint não muda?

Uso:  set MULTIPERFIL_PROXY=socks5://usuario:senha@host:porta
      .venv\\Scripts\\python prototipo\\spike_login.py
Rodar DUAS vezes. Na primeira, fazer login à mão na janela e apertar Enter.
"""

import asyncio
import hashlib
import json
import os
from pathlib import Path

from camoufox.ip import public_ip
from camoufox.geolocation import get_geolocation
from camoufox.utils import launch_options
from playwright.async_api import async_playwright

from multiperfil.fingerprint import gerar_congelado
from multiperfil.lancador import Lancador
from multiperfil.proxy import parse_proxy, testar
from multiperfil.repositorio import Perfil

PASTA = Path("dados/spike")
SONDA = """() => {
  const c = document.createElement('canvas'); const g = c.getContext('2d');
  g.font = '16px Arial'; g.fillText('MultiPerfil 🦊', 2, 20);
  return {ua: navigator.userAgent, tela: [screen.width, screen.height],
          janela: [innerWidth, innerHeight], fuso: Intl.DateTimeFormat().resolvedOptions().timeZone,
          idioma: navigator.language, canvas: c.toDataURL()};
}"""


def _perfil() -> Perfil:
    PASTA.mkdir(parents=True, exist_ok=True)
    arquivo = PASTA / "config.json"
    if not arquivo.exists():
        arquivo.write_text(json.dumps(gerar_congelado("windows", launch_options)))
    proxy = parse_proxy(os.environ["MULTIPERFIL_PROXY"])
    print("proxy:", testar(proxy, public_ip, get_geolocation))
    return Perfil("spike", "Spike", "windows", proxy, json.loads(arquivo.read_text()), "")


async def main() -> None:
    perfil, lancador = _perfil(), Lancador()
    sessao = PASTA / "sessao.json"
    ws = lancador.abrir(perfil)
    print("ws:", ws)
    try:
        async with async_playwright() as pw:
            browser = await pw.firefox.connect(ws)
            ctx = await browser.new_context(
                no_viewport=True, storage_state=str(sessao) if sessao.exists() else None
            )
            page = await ctx.new_page()
            sonda = await page.evaluate(SONDA)
            sonda["canvas"] = hashlib.sha256(sonda["canvas"].encode()).hexdigest()[:16]
            print("fingerprint:", sonda)
            await page.goto("https://studio.youtube.com")
            input("Se pediu login, faça na janela. Depois aperte Enter aqui...")
            print("url final:", page.url)
            await ctx.storage_state(path=str(sessao))
            await browser.close()
    finally:
        lancador.fechar(perfil.id)


asyncio.run(main())
