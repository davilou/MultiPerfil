import http.server
import socket
import subprocess
import sys
import threading

import pytest

from multiperfil.proxy import Proxy
from multiperfil.rede import esperar_porta, porta_livre
from multiperfil.repassador import Repassador, uri_remota


class _Ok(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


@pytest.fixture
def destino():
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Ok)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    yield servidor.server_address[1]
    servidor.shutdown()


@pytest.fixture
def remoto_com_senha():
    porta = porta_livre()
    processo = subprocess.Popen(
        [sys.executable, "-m", "pproxy", "-l", f"http://127.0.0.1:{porta}#ana:segredo"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    esperar_porta(porta, processo, prazo_s=10)
    yield porta
    processo.kill()
    processo.wait()


def _get_via(porta_proxy: int, porta_destino: int) -> bytes:
    with socket.create_connection(("127.0.0.1", porta_proxy), timeout=10) as s:
        s.sendall(f"GET http://127.0.0.1:{porta_destino}/ HTTP/1.1\r\n"
                  f"Host: 127.0.0.1:{porta_destino}\r\nConnection: close\r\n\r\n".encode())
        resposta = b""
        while dados := s.recv(4096):
            resposta += dados
    return resposta


def test_uri_remota_sem_senha_na_uri(tmp_path):
    auth = tmp_path / "a.auth"
    assert uri_remota(Proxy("http", "h", 1, "u", "s"), auth) == f"http://h:1##{auth}"
    assert uri_remota(Proxy("socks5", "h", 1), None) == "socks5://h:1"
    assert uri_remota(Proxy("https", "h", 1), None) == "http+ssl://h:1"


def test_encaminha_com_senha_e_limpa_arquivo(tmp_path, destino, remoto_com_senha):
    repassador = Repassador(tmp_path)
    porta = repassador.abrir("t", Proxy("http", "127.0.0.1", remoto_com_senha, "ana", "segredo"))
    assert (tmp_path / "t.auth").exists()
    assert _get_via(porta, destino).endswith(b"ok")
    repassador.fechar("t")
    assert not (tmp_path / "t.auth").exists()


def test_senha_errada_nao_passa(tmp_path, destino, remoto_com_senha):
    repassador = Repassador(tmp_path)
    porta = repassador.abrir("t", Proxy("http", "127.0.0.1", remoto_com_senha, "ana", "errada"))
    try:
        assert not _get_via(porta, destino).endswith(b"ok")
    finally:
        repassador.fechar("t")


def test_abrir_duas_vezes_troca_o_processo(tmp_path, remoto_com_senha):
    repassador = Repassador(tmp_path)
    proxy = Proxy("http", "127.0.0.1", remoto_com_senha, "ana", "segredo")
    primeira = repassador.abrir("t", proxy)
    segunda = repassador.abrir("t", proxy)
    assert primeira != segunda
    repassador.fechar("t")
