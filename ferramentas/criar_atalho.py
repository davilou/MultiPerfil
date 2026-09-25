"""Cria o atalho "MultiPerfil" na Área de Trabalho: duplo clique abre o app, sem terminal.

Uso: .venv\\Scripts\\python ferramentas\\criar_atalho.py
"""

import os
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# Caminhos entram por variável de ambiente: o script PowerShell não precisa de aspas
# escapadas e nada do usuário é interpolado como código.
SCRIPT = r"""
$desktop = [Environment]::GetFolderPath('Desktop')
$atalho = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $desktop 'MultiPerfil.lnk'))
$atalho.TargetPath = $env:MP_ALVO
$atalho.Arguments = '-m multiperfil.app'
$atalho.WorkingDirectory = $env:MP_RAIZ
$atalho.Description = 'MultiPerfil - perfis de navegador com proxy e fingerprint'
$atalho.Save()
Write-Output (Join-Path $desktop 'MultiPerfil.lnk')
"""


def main() -> None:
    alvo = RAIZ / ".venv" / "Scripts" / "pythonw.exe"
    if not alvo.exists():
        raise SystemExit(f"pythonw não encontrado em {alvo}; crie o venv antes")
    ambiente = {**os.environ, "MP_ALVO": str(alvo), "MP_RAIZ": str(RAIZ)}
    resultado = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", SCRIPT],
        env=ambiente, capture_output=True, text=True, check=True,
    )
    print("atalho criado:", resultado.stdout.strip())


if __name__ == "__main__":
    main()
