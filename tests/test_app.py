from multiperfil.app import encerrar_perfis
from multiperfil.estado import Registro


class _Repo:
    def listar(self):
        from multiperfil.repositorio import Perfil
        return [Perfil(i, i, "windows", None, 1, "pt-BR", "") for i in ("a", "b", "c")]


class _LancadorQueFalhaNoPrimeiro:
    def __init__(self):
        self.fechados = []

    def fechar(self, perfil_id):
        if perfil_id == "a":
            raise RuntimeError("falhou")
        self.fechados.append(perfil_id)


def test_encerrar_fecha_os_outros_mesmo_se_um_falhar():
    registro = Registro()
    for pid in ("a", "b", "c"):
        registro.reservar(pid)
    lancador = _LancadorQueFalhaNoPrimeiro()
    encerrar_perfis(_Repo(), lancador, registro)
    assert lancador.fechados == ["b", "c"]
