"""`python -m multiperfil` — sobe a API em 127.0.0.1:8800 com as dependências reais."""

import logging
import os
import secrets
from pathlib import Path

import uvicorn
from camoufox.ip import public_ip

from multiperfil.api import Dependencias, criar_app
from multiperfil.estado import Registro
from multiperfil.geo import localizar
from multiperfil.lancador import Lancador
from multiperfil.proxy import testar
from multiperfil.repassador import Repassador
from multiperfil.repositorio import Repositorio

PORTA = 8800
NAVEGADOR_PADRAO = "navegador/ungoogled-chromium_148.0.7778.215-1.1_windows_x64/chrome.exe"


def montar_dependencias(dados: Path, navegador: Path) -> Dependencias:
    pasta_perfis = dados / "perfis"
    return Dependencias(
        repo=Repositorio(dados / "perfis.db"),
        lancador=Lancador(navegador, pasta_perfis, Repassador(dados / "repassadores")),
        registro=Registro(),
        pasta_perfis=pasta_perfis,
        nova_seed=lambda: secrets.randbelow(2**31 - 1) + 1,
        testar_proxy=lambda proxy: testar(proxy, public_ip, localizar),
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    dados = Path(os.environ.get("MULTIPERFIL_DADOS", "dados")).resolve()
    navegador = Path(os.environ.get("MULTIPERFIL_NAVEGADOR", NAVEGADOR_PADRAO)).resolve()
    uvicorn.run(criar_app(montar_dependencias(dados, navegador)), host="127.0.0.1", port=PORTA)


if __name__ == "__main__":
    main()
