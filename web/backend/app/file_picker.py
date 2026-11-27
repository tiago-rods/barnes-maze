"""Diálogo nativo de abrir arquivo, para o passo "carregar vídeo" do wizard.

Frontend e backend rodam na mesma máquina (ferramenta local) — por isso o
diálogo é aberto aqui, pelo processo do backend, em vez de um
`<input type="file">` do navegador: esse elemento nunca expõe o caminho
absoluto do arquivo (só o nome), e o resto do wizard trabalha com caminhos
de arquivo, não upload (ver `routers/videos.py`, `data/` compartilhada).

Roda o diálogo num SUBPROCESSO, não na thread da requisição: o FastAPI
executa rotas síncronas numa threadpool (nunca a thread principal do
processo), e o Tcl/Tk do `tkinter` espera ser criado e manipulado pela
thread principal — chamá-lo de uma thread secundária chegou a derrubar o
processo inteiro do backend (não só a requisição). Isolar num processo novo
evita esse problema de afinidade de thread por completo: a thread
principal do subprocesso é a dele mesmo.
"""

from __future__ import annotations

import subprocess
import sys

_DIALOG_SCRIPT = """
import sys
import tkinter as tk
from tkinter import filedialog

initial_dir = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else None
root = tk.Tk()
root.withdraw()
root.attributes("-topmost", True)
path = filedialog.askopenfilename(
    title="Selecionar vídeo",
    initialdir=initial_dir,
    filetypes=[("Videos MP4", "*.mp4"), ("Todos os arquivos", "*.*")],
)
root.destroy()
print(path)
"""


def pick_video_file(initial_dir: str | None = None) -> str | None:
    """Abre o Explorador de Arquivos nativo para escolher um vídeo .mp4.

    Args:
        initial_dir: Pasta inicial do diálogo, se houver.

    Returns:
        O caminho absoluto escolhido, ou `None` se o operador cancelar.

    Raises:
        RuntimeError: Se o subprocesso do diálogo falhar.
    """
    result = subprocess.run(
        [sys.executable, "-c", _DIALOG_SCRIPT, initial_dir or ""],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Falha ao abrir o Explorador de Arquivos: {result.stderr.strip()}"
        )
    path = result.stdout.strip()
    return path or None
