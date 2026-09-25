from multiperfil.lancador import achar_endpoint, comando_matar_arvore, limpar_linha


def test_acha_endpoint_com_ansi():
    linha = "Websocket endpoint:\x1b[93m ws://localhost:51234/abc123 \x1b[0m\n"
    assert achar_endpoint(linha) == "ws://localhost:51234/abc123"


def test_linha_sem_endpoint():
    assert achar_endpoint("Launching server...\n") is None


def test_comando_matar_arvore_no_windows():
    assert comando_matar_arvore(1234, "nt") == ["taskkill", "/pid", "1234", "/T", "/F"]


def test_comando_matar_arvore_fora_do_windows():
    assert comando_matar_arvore(1234, "posix") is None


def test_limpar_linha_remove_ansi_e_mascara_segredo():
    linha = "\x1b[93mproxy user:senha123@host\x1b[0m\n"
    assert limpar_linha(linha, ("senha123",)) == "proxy user:***@host\n"


def test_limpar_linha_mascara_forma_url_encoded_tambem():
    linha = "proxy user:senha%20123@host\n"
    assert limpar_linha(linha, ("senha123", "senha%20123")) == "proxy user:***@host\n"


def test_limpar_linha_sem_segredos():
    assert limpar_linha("Launching server...\n", ()) == "Launching server...\n"


def test_limpar_linha_ignora_segredo_vazio():
    assert limpar_linha("texto qualquer\n", ("",)) == "texto qualquer\n"
