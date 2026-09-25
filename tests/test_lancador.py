from multiperfil.lancador import achar_endpoint


def test_acha_endpoint_com_ansi():
    linha = "Websocket endpoint:\x1b[93m ws://localhost:51234/abc123 \x1b[0m\n"
    assert achar_endpoint(linha) == "ws://localhost:51234/abc123"


def test_linha_sem_endpoint():
    assert achar_endpoint("Launching server...\n") is None
