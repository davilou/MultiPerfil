import pytest
from fastapi.testclient import TestClient

from multiperfil.api import Dependencias, criar_app
from multiperfil.estado import Registro
from multiperfil.proxy import ErroProxy, ResultadoProxy
from multiperfil.repositorio import Repositorio


class LancadorFalso:
    def __init__(self) -> None:
        self.abertos: dict[str, int | None] = {}
        self.fusos: list[str] = []

    def abrir(self, perfil, fuso: str) -> str:
        self.fusos.append(fuso)
        self.abertos[perfil.id] = None
        return f"http://127.0.0.1:9/{perfil.id}"

    def vivo(self, perfil_id: str) -> bool:
        return perfil_id in self.abertos and self.abertos[perfil_id] is None

    def codigo_saida(self, perfil_id: str) -> int | None:
        return self.abertos.get(perfil_id)

    def fechar(self, perfil_id: str) -> None:
        self.abertos.pop(perfil_id, None)


def _proxy_ok(proxy):
    return ResultadoProxy("5.6.7.8", "SK", "Europe/Bratislava", 120)


def _proxy_morto(proxy):
    raise ErroProxy("proxy http://u:***@h:1 não respondeu")


@pytest.fixture
def montar(tmp_path):
    def _montar(testar=_proxy_ok):
        lancador = LancadorFalso()
        deps = Dependencias(
            repo=Repositorio(tmp_path / "p.db"),
            lancador=lancador,
            registro=Registro(),
            pasta_perfis=tmp_path / "perfis",
            nova_seed=lambda: 777,
            testar_proxy=testar,
        )
        return TestClient(criar_app(deps)), lancador, deps
    return _montar


NOVO = {"id": "canal-a", "nome": "Canal A", "proxy": "http://u:segredo@h:1"}


def test_criar_com_padroes_e_listar_sem_senha(montar):
    cliente, _, deps = montar()
    assert cliente.post("/perfis", json=NOVO).status_code == 201
    perfil = cliente.get("/perfis").json()[0]
    assert perfil["proxy"] == "http://u:***@h:1"
    assert (perfil["sistema"], perfil["idioma"], perfil["status"]) == ("windows", "pt-BR", "fechado")
    assert deps.repo.obter("canal-a").seed == 777
    assert "segredo" not in cliente.get("/perfis").text


def test_criar_duplicado_409_e_invalidos_422(montar):
    cliente, _, _ = montar()
    cliente.post("/perfis", json=NOVO)
    assert cliente.post("/perfis", json=NOVO).status_code == 409
    assert cliente.post("/perfis", json={**NOVO, "id": "b", "proxy": "lixo"}).status_code == 422
    assert cliente.post("/perfis", json={**NOVO, "id": "c", "idioma": "xx_YY"}).status_code == 422
    assert cliente.post("/perfis", json={**NOVO, "id": "Com Espaço"}).status_code == 422


def test_abrir_usa_fuso_do_proxy_e_devolve_cdp(montar):
    cliente, lancador, _ = montar()
    cliente.post("/perfis", json=NOVO)
    r = cliente.post("/perfis/canal-a/abrir")
    assert r.status_code == 200
    assert r.json() == {"cdp": "http://127.0.0.1:9/canal-a"}
    assert lancador.fusos == ["Europe/Bratislava"]
    assert cliente.get("/perfis/canal-a/status").json()["status"] == "aberto"


def test_abrir_duas_vezes_409_com_cdp(montar):
    cliente, _, _ = montar()
    cliente.post("/perfis", json=NOVO)
    cliente.post("/perfis/canal-a/abrir")
    r = cliente.post("/perfis/canal-a/abrir")
    assert r.status_code == 409
    assert r.json()["detail"]["cdp"] == "http://127.0.0.1:9/canal-a"


def test_proxy_morto_nao_abre(montar):
    cliente, lancador, _ = montar(testar=_proxy_morto)
    cliente.post("/perfis", json=NOVO)
    assert cliente.post("/perfis/canal-a/abrir").status_code == 502
    assert lancador.abertos == {}
    assert cliente.get("/perfis/canal-a/status").json()["status"] == "fechado"


def test_janela_fechada_na_mao_vira_fechado(montar):
    cliente, lancador, _ = montar()
    cliente.post("/perfis", json=NOVO)
    cliente.post("/perfis/canal-a/abrir")
    lancador.abertos["canal-a"] = 0
    assert cliente.get("/perfis/canal-a/status").json()["status"] == "fechado"
    assert "canal-a" not in lancador.abertos


def test_navegador_que_quebrou_vira_erro(montar):
    cliente, lancador, _ = montar()
    cliente.post("/perfis", json=NOVO)
    cliente.post("/perfis/canal-a/abrir")
    lancador.abertos["canal-a"] = 5
    corpo = cliente.get("/perfis/canal-a/status").json()
    assert corpo["status"] == "erro"
    assert "5" in corpo["erro"]


def test_editar_e_remover_bloqueados_enquanto_aberto(montar):
    cliente, _, _ = montar()
    cliente.post("/perfis", json=NOVO)
    cliente.post("/perfis/canal-a/abrir")
    edicao = {"nome": "X", "proxy": "http://h:2", "idioma": "en-US", "notas": ""}
    assert cliente.patch("/perfis/canal-a", json=edicao).status_code == 409
    assert cliente.delete("/perfis/canal-a").status_code == 409
    assert cliente.post("/perfis/canal-a/fechar").json() == {"status": "fechado"}
    assert cliente.patch("/perfis/canal-a", json=edicao).json()["idioma"] == "en-US"


def test_remover_apaga_pasta_do_perfil(montar):
    cliente, _, deps = montar()
    cliente.post("/perfis", json=NOVO)
    pasta = deps.pasta_perfis / "canal-a"
    pasta.mkdir(parents=True)
    (pasta / "Cookies").write_text("x")
    assert cliente.delete("/perfis/canal-a").status_code == 204
    assert not pasta.exists()


def test_perfil_inexistente_404(montar):
    cliente, _, _ = montar()
    assert cliente.post("/perfis/nada/abrir").status_code == 404


def test_remover_com_arquivo_em_uso_da_409_e_mantem_perfil(montar):
    cliente, _, deps = montar()
    cliente.post("/perfis", json=NOVO)
    pasta = deps.pasta_perfis / "canal-a"
    pasta.mkdir(parents=True)
    with open(pasta / "Cookies", "w") as preso:  # no Windows, arquivo aberto não apaga
        preso.write("x")
        resposta = cliente.delete("/perfis/canal-a")
    assert resposta.status_code == 409
    assert cliente.get("/perfis").json()[0]["id"] == "canal-a"


def test_saida_tem_campos_da_tabela(montar):
    cliente, _, _ = montar()
    cliente.post("/perfis", json=NOVO)
    p = cliente.get("/perfis").json()[0]
    for campo in ("favorito", "criado_em", "editado_em", "ultimo_inicio", "pais", "ip_saida", "cdp"):
        assert campo in p
    assert p["cdp"] is None


def test_abrir_registra_inicio_teste_e_cdp_na_lista(montar):
    cliente, _, _ = montar()
    cliente.post("/perfis", json=NOVO)
    cliente.post("/perfis/canal-a/abrir")
    p = cliente.get("/perfis").json()[0]
    assert p["ultimo_inicio"] and (p["pais"], p["ip_saida"]) == ("SK", "5.6.7.8")
    assert p["cdp"] == "http://127.0.0.1:9/canal-a"


def test_testar_proxy_registra_pais(montar):
    cliente, _, _ = montar()
    cliente.post("/perfis", json=NOVO)
    cliente.post("/perfis/canal-a/testar-proxy")
    assert cliente.get("/perfis").json()[0]["pais"] == "SK"


def test_favorito(montar):
    cliente, _, _ = montar()
    cliente.post("/perfis", json=NOVO)
    assert cliente.put("/perfis/canal-a/favorito", json={"favorito": True}).json()["favorito"] is True
    assert cliente.put("/perfis/nada/favorito", json={"favorito": True}).status_code == 404


def test_editar_com_proxy_mascarado_mantem_senha(montar):
    cliente, _, deps = montar()
    cliente.post("/perfis", json=NOVO)
    mascarado = cliente.get("/perfis").json()[0]["proxy"]
    edicao = {"nome": "Novo", "proxy": mascarado, "idioma": "pt-BR", "notas": ""}
    assert cliente.patch("/perfis/canal-a", json=edicao).status_code == 200
    assert deps.repo.obter("canal-a").proxy.senha == "segredo"


def test_pagina_do_app(montar):
    cliente, _, _ = montar()
    r = cliente.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]


def test_criar_devolve_datas_do_banco(montar):
    cliente, _, _ = montar()
    corpo = cliente.post("/perfis", json=NOVO).json()
    assert corpo["criado_em"] and corpo["editado_em"] == corpo["criado_em"]


def test_lista_traz_mensagem_de_erro(montar):
    cliente, lancador, _ = montar()
    cliente.post("/perfis", json=NOVO)
    cliente.post("/perfis/canal-a/abrir")
    lancador.abertos["canal-a"] = 5
    p = cliente.get("/perfis").json()[0]
    assert p["status"] == "erro" and "5" in p["erro"]


def test_mostrar_janela_chama_o_app(tmp_path):
    chamadas = []
    deps = Dependencias(repo=Repositorio(tmp_path / "p.db"), lancador=LancadorFalso(),
                        registro=Registro(), pasta_perfis=tmp_path / "perfis",
                        nova_seed=lambda: 1, testar_proxy=_proxy_ok)
    cliente = TestClient(criar_app(deps, mostrar_janela=lambda: chamadas.append(1)))
    assert cliente.post("/janela/mostrar").status_code == 204
    assert chamadas == [1]


def test_mostrar_janela_sem_app_da_404(montar):
    cliente, _, _ = montar()
    assert cliente.post("/janela/mostrar").status_code == 404


def test_checar_proxy_sem_salvar(montar):
    cliente, _, deps = montar()
    r = cliente.post("/proxy/testar", json={"proxy": "http://u:segredo@h:1"})
    assert r.status_code == 200 and r.json()["pais"] == "SK"
    assert deps.repo.listar() == []


def test_checar_proxy_mascarado_usa_o_salvo(tmp_path):
    vistos = []
    def testar(proxy):
        vistos.append(proxy)
        return _proxy_ok(proxy)
    deps = Dependencias(repo=Repositorio(tmp_path / "p.db"), lancador=LancadorFalso(),
                        registro=Registro(), pasta_perfis=tmp_path / "perfis",
                        nova_seed=lambda: 1, testar_proxy=testar)
    cliente = TestClient(criar_app(deps))
    cliente.post("/perfis", json=NOVO)
    mascarado = cliente.get("/perfis").json()[0]["proxy"]
    r = cliente.post("/proxy/testar", json={"proxy": mascarado, "perfil_id": "canal-a"})
    assert r.status_code == 200
    assert vistos[-1].senha == "segredo"


def test_checar_proxy_invalido_422_e_morto_502(montar):
    cliente, _, _ = montar(testar=_proxy_morto)
    assert cliente.post("/proxy/testar", json={"proxy": "lixo"}).status_code == 422
    r = cliente.post("/proxy/testar", json={"proxy": "http://u:segredo@h:1"})
    assert r.status_code == 502 and "segredo" not in r.text


SEM_PROXY = {"id": "pessoal", "nome": "Pessoal", "proxy": ""}


def test_criar_e_abrir_sem_proxy_nao_testa_proxy(montar):
    testados = []
    cliente, lancador, _ = montar(testar=lambda p: testados.append(p) or _proxy_ok(p))
    assert cliente.post("/perfis", json=SEM_PROXY).status_code == 201
    p = cliente.get("/perfis").json()[0]
    assert p["proxy"] is None
    assert cliente.post("/perfis/pessoal/abrir").status_code == 200
    assert testados == [] and lancador.fusos == [None]


def test_editar_tira_e_poe_proxy(montar):
    cliente, _, deps = montar()
    cliente.post("/perfis", json=NOVO)
    base = {"nome": "A", "idioma": "pt-BR", "notas": ""}
    assert cliente.patch("/perfis/canal-a", json={**base, "proxy": ""}).json()["proxy"] is None
    assert deps.repo.obter("canal-a").proxy is None
    r = cliente.patch("/perfis/canal-a", json={**base, "proxy": "http://h:2"})
    assert r.json()["proxy"] == "http://h:2"


def test_testar_proxy_de_perfil_sem_proxy_da_409(montar):
    cliente, _, _ = montar()
    cliente.post("/perfis", json=SEM_PROXY)
    assert cliente.post("/perfis/pessoal/testar-proxy").status_code == 409


def test_checar_proxy_vazio_da_422(montar):
    cliente, _, _ = montar()
    assert cliente.post("/proxy/testar", json={"proxy": "  "}).status_code == 422
