"""App desktop: API numa thread + janela pywebview. Fechar a janela fecha tudo.

Rodar: .venv\\Scripts\\pythonw -m multiperfil.app   (pythonw: sem janela de terminal)
"""

from __future__ import annotations

import logging
import os
import socket
import threading
import urllib.request
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


def pedir_para_aparecer() -> bool:
    """Já existe um MultiPerfil aberto? Pede a ele que traga a janela à frente."""
    pedido = urllib.request.Request(f"http://127.0.0.1:{PORTA}/janela/mostrar", method="POST")
    try:
        with urllib.request.urlopen(pedido, timeout=3) as resposta:
            return resposta.status == 204
    except OSError:
        return False


def trazer_a_frente(janela: webview.Window) -> None:
    janela.restore()
    janela.show()
    janela.on_top = True  # no Windows, alternar on_top é o que tira a janela de trás
    janela.on_top = False


def avisar_porta_em_uso() -> None:
    webview.create_window("MultiPerfil", html="<p style='font:14px sans-serif;padding:24px'>"
                          f"Outro programa está usando a porta {PORTA}. Feche-o e abra o "
                          "MultiPerfil de novo.</p>", width=460, height=170)
    webview.start()


def main() -> None:
    os.chdir(RAIZ)  # o atalho pode abrir com outra pasta de trabalho
    dados = RAIZ / "dados"
    logging.basicConfig(filename=dados / "app.log", level=logging.INFO,
                        format="%(asctime)s %(name)s %(message)s")
    if porta_ocupada(PORTA):
        if not pedir_para_aparecer():
            avisar_porta_em_uso()
        return
    deps = montar_dependencias(dados, (RAIZ / NAVEGADOR_PADRAO).resolve())
    janela = webview.create_window("MultiPerfil", f"http://127.0.0.1:{PORTA}/",
                                   width=1400, height=860, min_size=(1000, 600))
    app = criar_app(deps, mostrar_janela=lambda: trazer_a_frente(janela))
    servidor = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORTA, log_config=None))
    threading.Thread(target=servidor.run, daemon=True).start()
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
