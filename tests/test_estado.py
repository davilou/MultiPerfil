import pytest

from multiperfil.estado import PerfilJaAberto, Registro, Status


def test_perfil_desconhecido_esta_fechado():
    assert Registro().status("a").status is Status.FECHADO


def test_reservar_abrir_e_liberar():
    r = Registro()
    r.reservar("a")
    assert r.status("a").status is Status.ABRINDO
    r.marcar_aberto("a", "ws://x")
    assert (r.status("a").status, r.status("a").ws) == (Status.ABERTO, "ws://x")
    r.liberar("a")
    assert r.status("a").status is Status.FECHADO


@pytest.mark.parametrize("ws", [None, "ws://x"])
def test_segunda_reserva_falha_com_ws_existente(ws):
    r = Registro()
    r.reservar("a")
    if ws:
        r.marcar_aberto("a", ws)
    with pytest.raises(PerfilJaAberto) as erro:
        r.reservar("a")
    assert erro.value.ws == ws


def test_perfil_em_erro_pode_reabrir():
    r = Registro()
    r.reservar("a")
    r.marcar_erro("a", "caiu")
    assert (r.status("a").status, r.status("a").erro) == (Status.ERRO, "caiu")
    r.reservar("a")
    assert r.status("a").status is Status.ABRINDO


def test_ocupado():
    r = Registro()
    assert not r.ocupado("a")
    r.reservar("a")
    assert r.ocupado("a")
