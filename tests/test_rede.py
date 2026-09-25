import socket
import subprocess
import sys

import pytest

from multiperfil.rede import ErroRede, esperar_porta, porta_livre


def test_porta_livre_esta_livre():
    porta = porta_livre()
    with socket.socket() as s:
        s.bind(("127.0.0.1", porta))


def test_esperar_porta_que_abre():
    with socket.socket() as servidor:
        servidor.bind(("127.0.0.1", 0))
        servidor.listen()
        processo = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
        try:
            esperar_porta(servidor.getsockname()[1], processo, prazo_s=2)
        finally:
            processo.kill()


def test_esperar_porta_falha_se_processo_morre():
    processo = subprocess.Popen([sys.executable, "-c", "raise SystemExit(3)"])
    with pytest.raises(ErroRede, match="código 3"):
        esperar_porta(porta_livre(), processo, prazo_s=5)
