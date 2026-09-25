"""App desktop: API numa thread + janela pywebview. Fechar a janela fecha tudo.

Rodar: .venv\\Scripts\\pythonw -m multiperfil.app   (pythonw: sem janela de terminal)
"""

from __future__ import annotations

import logging
import os
import socket
import threading
from pathlib import Path

import uvicorn
import webview

from multiperfil.__main__ import NAVEGADOR_PADRAO, PORTA, montar_dependencias
from multiperfil.api import Dependencias, criar_app

RAIZ = Path(__file__).resolve().parent.parent
log = logging.getLogger("multiperfil.app")


def porta_ocupada(porta: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", porta)) == 0


def main() -> None:
    os.chdir(RAIZ)  # o atalho pode abrir com outra pasta de trabalho
    dados = RAIZ / "dados"
    logging.basicConfig(filename=dados / "app.log", level=logging.INFO,
                        format="%(asctime)s %(name)s %(message)s")
    if porta_ocupada(PORTA):
        webview.create_window("MultiPerfil", html="<p style='font:14px sans-serif;padding:24px'>"
                              "O MultiPerfil já está aberto (porta 8800 em uso).</p>",
                              width=420, height=160)
        webview.start()
        return
    deps = montar_dependencias(dados, (RAIZ / NAVEGADOR_PADRAO).resolve())
    servidor = uvicorn.Server(uvicorn.Config(criar_app(deps), host="127.0.0.1", port=PORTA,
                                             log_config=None))
    threading.Thread(target=servidor.run, daemon=True).start()
    janela = webview.create_window("MultiPerfil", f"http://127.0.0.1:{PORTA}/",
                                   width=1400, height=860, min_size=(1000, 600))
    janela.events.closed += lambda: _encerrar(deps, servidor)
    webview.start()


def _encerrar(deps: Dependencias, servidor: uvicorn.Server) -> None:
    """Fecha os perfis abertos pelo CDP (grava cookies) e para a API."""
    for perfil in deps.repo.listar():
        if deps.registro.ocupado(perfil.id):
            deps.lancador.fechar(perfil.id)
            deps.registro.liberar(perfil.id)
    servidor.should_exit = True


if __name__ == "__main__":
    main()
