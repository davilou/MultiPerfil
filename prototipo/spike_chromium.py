"""Portão 2: fingerprint-chromium com pasta de perfil persistente, seed fixa e CDP.

Mede: login persiste? fingerprint igual entre aberturas? fuso do proxy? Studio mais
rápido com o cache da 2ª abertura? O proxy (com senha) passa por um repassador local
(pproxy) que lê as credenciais de arquivo — a senha não vai para linha de comando.

Rodar DUAS vezes. Na 1ª, fazer login à mão na janela; o script espera sozinho.
"""

import asyncio
import hashlib
import json
import random
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from camoufox.ip import public_ip
from playwright.async_api import async_playwright

from multiperfil.geo import localizar
from multiperfil.proxy import Proxy, parse_proxy, testar

PASTA = Path("dados/spike-chromium").resolve()
CHROME = Path("navegador/ungoogled-chromium_148.0.7778.215-1.1_windows_x64/chrome.exe").resolve()
PRAZO_LOGIN_MS = 10 * 60 * 1000
INICIO = time.perf_counter()
SONDA = """() => {
  const c = document.createElement('canvas'); const g = c.getContext('2d');
  g.font = '16px Arial'; g.fillText('MultiPerfil', 2, 20);
  return {ua: navigator.userAgent, tela: [screen.width, screen.height],
          janela: [innerWidth, innerHeight], fuso: Intl.DateTimeFormat().resolvedOptions().timeZone,
          idioma: navigator.language, canvas: c.toDataURL()};
}"""


def marca(texto: str) -> None:
    print(f"[{time.perf_counter() - INICIO:6.1f}s] {texto}", flush=True)


def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def seed_do_perfil() -> int:
    arquivo = PASTA / "seed.txt"
    if not arquivo.exists():
        arquivo.write_text(str(random.randint(1, 2**31 - 1)))
    return int(arquivo.read_text())


def subir_repassador(proxy: Proxy, porta: int) -> subprocess.Popen:
    auth = PASTA / "proxy.auth"
    auth.write_text(f"{proxy.usuario}:{proxy.senha}" if proxy.usuario else "", encoding="utf-8")
    remoto = f"{proxy.esquema}://{proxy.host}:{proxy.porta}" + (f"##{auth}" if proxy.usuario else "")
    return subprocess.Popen(
        [sys.executable, "-m", "pproxy", "-l", f"http://127.0.0.1:{porta}", "-r", remoto],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def subir_chrome(seed: int, fuso: str, idioma: str, porta_px: int, porta_cdp: int) -> subprocess.Popen:
    return subprocess.Popen([
        str(CHROME),
        f"--user-data-dir={PASTA / 'perfil'}",
        f"--fingerprint={seed}",
        "--fingerprint-platform=windows",
        f"--timezone={fuso}",
        f"--lang={idioma}",
        f"--accept-lang={idioma},{idioma.split('-')[0]}",
        f"--proxy-server=http://127.0.0.1:{porta_px}",
        f"--remote-debugging-port={porta_cdp}",
        "--no-first-run",
        "--no-default-browser-check",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def esperar_cdp(porta: int, prazo_s: float = 30) -> None:
    limite = time.monotonic() + prazo_s
    while time.monotonic() < limite:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{porta}/json/version", timeout=1).read()
            return
        except OSError:
            time.sleep(0.2)
    raise TimeoutError(f"CDP não respondeu em {prazo_s}s")


async def sessao(porta_cdp: int) -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{porta_cdp}")
        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        marca("conectado por CDP")
        sonda = await page.evaluate(SONDA)
        sonda["canvas"] = hashlib.sha256(sonda["canvas"].encode()).hexdigest()[:16]
        print("fingerprint:", json.dumps(sonda, ensure_ascii=False), flush=True)
        marca("abrindo studio")
        await page.goto("https://studio.youtube.com", timeout=120_000)
        print("pediu login:", "accounts.google.com" in page.url, flush=True)
        await page.wait_for_url("https://studio.youtube.com/**", timeout=PRAZO_LOGIN_MS)
        await page.wait_for_load_state("load")
        marca(f"studio carregado: {page.url[:70]}")
        cdp = await browser.new_browser_cdp_session()
        await cdp.send("Browser.close")  # fecha limpo: o Chrome grava cookies e cache


def main() -> None:
    PASTA.mkdir(parents=True, exist_ok=True)
    proxy = parse_proxy(Path("dados/proxy.txt").read_text(encoding="utf-8"))
    resultado = testar(proxy, public_ip, localizar)
    idioma = "pt-BR"
    marca(f"proxy ok: {resultado.pais} {resultado.fuso} {idioma}")
    porta_px, porta_cdp = porta_livre(), porta_livre()
    repassador = subir_repassador(proxy, porta_px)
    chrome = subir_chrome(seed_do_perfil(), resultado.fuso, idioma, porta_px, porta_cdp)
    try:
        esperar_cdp(porta_cdp)
        marca("chrome no ar")
        asyncio.run(sessao(porta_cdp))
        chrome.wait(timeout=20)
        marca("chrome fechou sozinho")
    finally:
        if chrome.poll() is None:
            subprocess.run(["taskkill", "/pid", str(chrome.pid), "/T", "/F"], capture_output=True)
            marca("chrome precisou ser morto")
        repassador.kill()
        (PASTA / "proxy.auth").unlink(missing_ok=True)


main()
