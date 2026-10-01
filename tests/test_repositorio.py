import sqlite3

import pytest

from multiperfil.proxy import Proxy
from multiperfil.repositorio import Perfil, PerfilExiste, PerfilInexistente, Repositorio, validar_id


def _perfil(pid: str = "canal-a") -> Perfil:
    return Perfil(
        id=pid,
        nome="Canal A",
        sistema="windows",
        proxy=Proxy("socks5", "h", 1080, "u", "p@ss"),
        seed=123456,
        idioma="pt-BR",
        notas="",
    )


def test_criar_obter_listar(tmp_path):
    repo = Repositorio(tmp_path / "p.db")
    repo.criar(_perfil())
    obtido = repo.obter("canal-a")
    assert obtido.proxy == Proxy("socks5", "h", 1080, "u", "p@ss")
    assert (obtido.seed, obtido.idioma) == (123456, "pt-BR")
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


def test_atualizar_nao_toca_na_seed(tmp_path):
    repo = Repositorio(tmp_path / "p.db")
    repo.criar(_perfil())
    repo.atualizar("canal-a", nome="Novo", proxy=Proxy("http", "x", 1), idioma="en-US", notas="n")
    p = repo.obter("canal-a")
    assert (p.nome, p.proxy, p.idioma, p.notas, p.seed) == (
        "Novo", Proxy("http", "x", 1), "en-US", "n", 123456)


@pytest.mark.parametrize("idioma", ["", "portugues", "pt_BR", "PT-br", "pt-BR;q=1"])
def test_idioma_invalido(tmp_path, idioma):
    repo = Repositorio(tmp_path / "p.db")
    with pytest.raises(ValueError):
        repo.criar(Perfil("a", "A", "windows", Proxy("http", "h", 1), 1, idioma, ""))


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


def test_datas_e_favorito_no_ciclo(tmp_path):
    repo = Repositorio(tmp_path / "p.db")
    repo.criar(_perfil())
    p = repo.obter("canal-a")
    assert p.favorito is False and p.ultimo_inicio is None
    assert p.criado_em and p.editado_em == p.criado_em
    repo.definir_favorito("canal-a", True)
    repo.registrar_inicio("canal-a", "2026-09-25T12:00:00+00:00")
    repo.registrar_teste("canal-a", ip="5.6.7.8", pais="SK")
    p = repo.obter("canal-a")
    assert (p.favorito, p.ultimo_inicio, p.ip_saida, p.pais) == (
        True, "2026-09-25T12:00:00+00:00", "5.6.7.8", "SK")


def test_atualizar_muda_editado_em(tmp_path):
    repo = Repositorio(tmp_path / "p.db")
    repo.criar(_perfil())
    antes = repo.obter("canal-a").editado_em
    repo.atualizar("canal-a", nome="Novo", proxy=Proxy("http", "x", 1), idioma="pt-BR", notas="")
    assert repo.obter("canal-a").editado_em > antes


def test_migra_banco_antigo_sem_perder_perfil(tmp_path):
    caminho = tmp_path / "p.db"
    con = sqlite3.connect(caminho)
    con.execute("""CREATE TABLE perfis (id TEXT PRIMARY KEY, nome TEXT NOT NULL,
        sistema TEXT NOT NULL, proxy TEXT NOT NULL, seed INTEGER NOT NULL,
        idioma TEXT NOT NULL, notas TEXT NOT NULL, criado_em TEXT NOT NULL)""")
    con.execute("INSERT INTO perfis VALUES ('velho','Velho','windows','http://h:1',7,'pt-BR','',"
                "'2026-09-25T10:00:00+00:00')")
    con.commit()
    con.close()
    p = Repositorio(caminho).obter("velho")
    assert (p.seed, p.favorito, p.editado_em) == (7, False, "2026-09-25T10:00:00+00:00")


@pytest.mark.parametrize("metodo,args", [
    ("definir_favorito", (True,)), ("registrar_inicio", ("x",)),
])
def test_marcadores_em_perfil_inexistente(tmp_path, metodo, args):
    with pytest.raises(PerfilInexistente):
        getattr(Repositorio(tmp_path / "p.db"), metodo)("nada", *args)


def test_perfil_sem_proxy(tmp_path):
    repo = Repositorio(tmp_path / "p.db")
    repo.criar(Perfil("a", "A", "windows", None, 1, "pt-BR", ""))
    assert repo.obter("a").proxy is None
    repo.atualizar("a", nome="A", proxy=Proxy("http", "h", 1), idioma="pt-BR", notas="")
    assert repo.obter("a").proxy == Proxy("http", "h", 1)
    repo.atualizar("a", nome="A", proxy=None, idioma="pt-BR", notas="")
    assert repo.obter("a").proxy is None
