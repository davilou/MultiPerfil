"""Com `python -m multiperfil` rodando e o perfil `teste` criado."""

import asyncio
import sys

from playwright.async_api import async_playwright

from multiperfil.cliente import abrir_perfil


async def main(perfil_id: str) -> None:
    async with async_playwright() as pw:
        async with abrir_perfil(perfil_id, pw) as ctx:
            page = await ctx.new_page()
            await page.goto("https://ipinfo.io/json")
            print(await page.inner_text("body"))


asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "teste"))
