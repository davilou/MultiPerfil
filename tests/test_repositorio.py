import pytest

from multiperfil.proxy import Proxy
from multiperfil.repositorio import Perfil, PerfilExiste, PerfilInexistente, Repositorio, validar_id


def _perfil(pid: str = "canal-a") -> Perfil:
    return Perfil(
        id=pid,
        nome="Canal A",
        sistema="windows",
        proxy=Proxy("socks5", "h", 1080, "u", "p@ss"),
        config={"canvas:seed": 7},
        notas="",
    )


def test_criar_obter_listar(tmp_path):
    repo = Repositorio(tmp_path / "p.db")
    repo.criar(_perfil())
    obtido = repo.obter("canal-a")
    assert obtido.proxy == Proxy("socks5", "h", 1080, "u", "p@ss")
    assert obtido.config == {"canvas:seed": 7}
    assert [p.id for p in repo.listar()] == ["canal-a"]


def test_persiste_entre_instancias(tmp_path):
    Repositorio(tmp_path / "p.db").criar(_perfil())
    assert Repositorio(tmp_path / "p.db").obter("canal-a").nome == "Canal A"


def test_criar_duplicado_falha(tmp_path):
    repo = Repositorio(tmp_path / "p.db")
    repo.criar(_perfil())
    with pytest.raises(PerfilExiste):
        repo.criar(_perfil())


def test_obter_inexistente_falha(tmp_path):
    with pytest.raises(PerfilInexistente):
        Repositorio(tmp_path / "p.db").obter("nada")


def test_atualizar_nao_toca_no_config(tmp_path):
    repo = Repositorio(tmp_path / "p.db")
    repo.criar(_perfil())
    repo.atualizar("canal-a", nome="Novo", proxy=Proxy("http", "x", 1), notas="n")
    p = repo.obter("canal-a")
    assert (p.nome, p.proxy, p.notas, p.config) == ("Novo", Proxy("http", "x", 1), "n", {"canvas:seed": 7})


def test_remover(tmp_path):
    repo = Repositorio(tmp_path / "p.db")
    repo.criar(_perfil())
    repo.remover("canal-a")
    with pytest.raises(PerfilInexistente):
        repo.remover("canal-a")


@pytest.mark.parametrize("pid", ["", "A", "com espaço", "../x", "a" * 41])
def test_id_invalido(pid):
    with pytest.raises(ValueError):
        validar_id(pid)
