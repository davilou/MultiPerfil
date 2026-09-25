"""Uso num script de publicação:

    async with async_playwright() as pw:
        async with abrir_perfil("canal-a", pw) as ctx:
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            ...

O login e o cache ficam na pasta do perfil; ao sair do bloco o perfil é fechado pela
API (Browser.close pelo CDP), com ou sem erro no meio.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
from playwright.async_api import BrowserContext, Playwright

URL_PADRAO = "http://127.0.0.1:8800"


class ErroPerfil(Exception):
    pass


def _checar(resposta: httpx.Response) -> dict:
    if resposta.is_error:
        raise ErroPerfil(f"{resposta.status_code}: {resposta.text}")
    return resposta.json()


@asynccontextmanager
async def abrir_perfil(
    perfil_id: str, pw: Playwright, url: str = URL_PADRAO
) -> AsyncIterator[BrowserContext]:
    async with httpx.AsyncClient(base_url=url, timeout=120) as http:
        dados = _checar(await http.post(f"/perfis/{perfil_id}/abrir"))
        try:
            browser = await pw.chromium.connect_over_cdp(dados["cdp"])
            yield browser.contexts[0]
        finally:
            _checar(await http.post(f"/perfis/{perfil_id}/fechar"))
