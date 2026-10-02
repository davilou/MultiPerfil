from multiperfil.favorito import GUID_NOME, aplicar_favorito_nome


def _barra(dados):
    return dados["roots"]["bookmark_bar"]["children"]


def test_arquivo_novo_ganha_o_favorito():
    dados = aplicar_favorito_nome({}, "Conta Eslováquia")
    primeiro = _barra(dados)[0]
    assert (primeiro["name"], primeiro["guid"], primeiro["type"]) == ("● Conta Eslováquia", GUID_NOME, "url")
    assert "checksum" not in dados


def test_preserva_os_favoritos_do_usuario_e_vai_para_o_inicio():
    dados = {"checksum": "abc", "version": 1, "roots": {
        "bookmark_bar": {"children": [{"id": "5", "guid": "x", "name": "Meu", "type": "url", "url": "https://a"}],
                         "id": "1", "name": "Barra", "type": "folder"},
        "other": {"children": [], "id": "2", "type": "folder"}}}
    dados = aplicar_favorito_nome(dados, "Mega Alemã")
    nomes = [n["name"] for n in _barra(dados)]
    assert nomes == ["● Mega Alemã", "Meu"]
    assert dados["roots"]["other"] == {"children": [], "id": "2", "type": "folder"}
    assert _barra(dados)[0]["id"] not in {"1", "2", "5"}
    assert "checksum" not in dados


def test_renomear_atualiza_o_mesmo_favorito_sem_duplicar():
    dados = aplicar_favorito_nome({}, "Antigo")
    dados["roots"]["bookmark_bar"]["children"].append({"id": "99", "guid": "y", "name": "Outro", "type": "url", "url": "u"})
    dados["roots"]["bookmark_bar"]["children"].reverse()  # usuário arrastou o nosso para o fim
    dados = aplicar_favorito_nome(dados, "Novo")
    nomes = [n["name"] for n in _barra(dados)]
    assert nomes == ["● Novo", "Outro"]
