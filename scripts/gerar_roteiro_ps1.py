"""Gera scripts/roteiro-demonstracao.ps1 a partir de docs/ROTEIRO-DEMONSTRACAO.md.

O .ps1 roda, em ordem, todos os blocos ```powershell do roteiro: mostra cada
comando e o executa no mesmo escopo, para as variáveis ($v1, $exp, $maze, $tc...)
passarem de um passo para o outro como no terminal. Antes de cada passo que abre
janela, pausa e mostra o que fazer nela. Comandos que falham de propósito (as
recusas dos cenários) não interrompem o script.

Uso, da raiz do repositório:
    uv run python scripts/gerar_roteiro_ps1.py

Não edite o .ps1 à mão: mude o roteiro e gere de novo.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROTEIRO = ROOT / "docs" / "ROTEIRO-DEMONSTRACAO.md"
SAIDA = ROOT / "scripts" / "roteiro-demonstracao.ps1"

# Blocos que não fazem sentido dentro do script.
PULAR = {
    "cd barnes-maze": "o script já roda na pasta do repositório",
}
# Opcional na Parte C (não na A.2, que precisa recriar o banco): fica comentado.
COMENTAR = ('DROP DATABASE IF EXISTS barnes_demo"',)

# Dicas para os passos com janela, na ordem em que aparecem no roteiro.
DICAS = [
    ("video load $v1", "B.4", "a janela mostra o primeiro quadro: n avança, p volta, q fecha."),
    (
        'maze create --experiment-id $exp --name "montagem demo"',
        "B.3",
        (
            "a = borda, h = buracos, arraste do centro ao buraco de referência, botão direito "
            "no alvo, +/- muda N, [ ] raio do buraco, Enter confirma (Esc e q também salvam)."
        ),
    ),
    (
        'maze create --experiment-id $exp --name "montagem completa"',
        "B.3",
        (
            "h acha o anel; arraste até o buraco escuro de cima à direita e marque o MESMO "
            "buraco como alvo (botão direito); Enter confirma."
        ),
    ),
    (
        "scale calibrate --video $v1",
        "B.5/B.8",
        (
            "clique nas pontas de dois diâmetros da plataforma (4 cliques) e Enter. "
            "Botão direito desfaz, R recomeça."
        ),
    ),
    (
        "scale verify",
        "B.5",
        "marque um terceiro diâmetro, na diagonal (2 cliques), e Enter.",
    ),
    (
        "scale calibrate --video $vc",
        "B.5",
        "os mesmos 4 cliques, agora no vídeo completo, e Enter.",
    ),
    (
        "pose review --trial $tc",
        "B.13",
        (
            "abre no trecho do focinho: d 5x e clique no focinho, d 5x e clique de novo, "
            "Enter; no trecho da cauda, Enter sem marcar; s salva."
        ),
    ),
]


def extrair(texto: str) -> list[tuple[str, str, list[str]]]:
    secoes: list[tuple[str, str, list[str]]] = []
    atual = None
    em_codigo = False
    buf: list[str] = []
    for linha in texto.replace("\r\n", "\n").split("\n"):
        if not em_codigo:
            if linha.startswith(("## O que dizer", "## Se algo")):
                atual = None
                continue
            m = re.match(r"^### ([AB]\.\d+)\s+(.*)$", linha)
            if m:
                atual = (m.group(1), m.group(2), [])
                secoes.append(atual)
                continue
            if linha.startswith("## Parte C"):
                atual = ("C", "Encerramento", [])
                secoes.append(atual)
                continue
        if linha.startswith("```powershell"):
            em_codigo, buf = True, []
            continue
        if em_codigo and linha.startswith("```"):
            em_codigo = False
            if atual is not None:
                atual[2].append("\n".join(buf))
            continue
        if em_codigo:
            buf.append(linha)
    return secoes


def literal(texto: str) -> str:
    """String PowerShell entre aspas simples (sem expansão de variáveis)."""
    return "'" + texto.replace("'", "''") + "'"


def abre_janela(bloco: str, ja_revisado: set[str]) -> str | None:
    primeira = bloco.strip().splitlines()[0]
    if not primeira.startswith("uv run barnes"):
        return None
    if "--no-interactive" in primeira or "--no-preview" in primeira:
        return None
    for chave, secao, dica in DICAS:
        if chave in primeira:
            if chave.startswith("pose review"):
                # Só a primeira revisão abre janela; a segunda diz "nenhum pendente".
                if chave in ja_revisado:
                    return None
                ja_revisado.add(chave)
            return f"{secao}: {dica}"
    return None


def gerar() -> str:
    secoes = extrair(ROTEIRO.read_text(encoding="utf-8"))
    out = [
        "# GERADO por scripts/gerar_roteiro_ps1.py a partir de docs/ROTEIRO-DEMONSTRACAO.md.",
        "# Não edite à mão: mude o roteiro e gere de novo.",
        "#",
        "# Uso (PowerShell, da raiz do repositório barnes-maze):",
        "#   powershell -ExecutionPolicy Bypass -File scripts\\roteiro-demonstracao.ps1",
        "#   ... -PausarEntrePassos   para parar a cada seção (bom para apresentar)",
        "#",
        "# Roda do começo ao fim: cada seção depende das variáveis das anteriores.",
        "# Antes, faça commit de tudo e confira os caminhos dos vídeos na A.3.",
        "param([switch]$PausarEntrePassos)",
        "$ErrorActionPreference = 'Continue'",
        "Set-Location (Split-Path -Parent $PSScriptRoot)",
        "",
        "function Titulo([string]$id, [string]$texto) {",
        "    Write-Host ''",
        "    Write-Host ('=' * 78) -ForegroundColor Cyan",
        "    Write-Host ($id + '  ' + $texto) -ForegroundColor Cyan",
        "    Write-Host ('=' * 78) -ForegroundColor Cyan",
        "}",
        "function Mostrar([string[]]$linhas) {",
        "    foreach ($l in $linhas) { Write-Host ('PS> ' + $l) -ForegroundColor DarkGray }",
        "}",
        "function Janela([string]$dica) {",
        "    Write-Host ''",
        "    Write-Host ('ABRE JANELA - ' + $dica) -ForegroundColor Yellow",
        "    Read-Host 'Enter para abrir a janela' | Out-Null",
        "}",
        "function Pausa {",
        "    if ($PausarEntrePassos) { Read-Host 'Enter para continuar' | Out-Null }",
        "}",
        "",
    ]
    revisado: set[str] = set()
    total = 0
    for sid, titulo, blocos in secoes:
        if not blocos:
            continue
        out.append(f"Titulo {literal(sid)} {literal(titulo)}")
        for bloco in blocos:
            linhas = bloco.split("\n")
            primeira = linhas[0].strip()
            if primeira in PULAR:
                out.append(f"# pulado ({PULAR[primeira]}): {primeira}")
                continue
            if sid == "C" and any(c in bloco for c in COMENTAR):
                out.append("# Opcional, apaga o banco de demonstração:")
                out.extend("# " + l for l in linhas)
                continue
            dica = abre_janela(bloco, revisado)
            if dica:
                out.append(f"Janela {literal(dica)}")
            if len(linhas) > 10:
                resumo = [linhas[0], f"... (script de {len(linhas)} linhas, ver o roteiro)"]
            else:
                resumo = linhas
            out.append("Mostrar @(" + ", ".join(literal(l) for l in resumo) + ")")
            out.extend(linhas)
            total += 1
        out.append("Pausa")
        out.append("")
    out.append("Write-Host ''")
    out.append("Write-Host 'Roteiro concluído.' -ForegroundColor Green")
    print(f"{total} blocos em {sum(1 for s in secoes if s[2])} seções -> {SAIDA}")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    # BOM: o PowerShell 5.1 lê .ps1 sem BOM como ANSI e estraga os acentos.
    SAIDA.write_bytes(b"\xef\xbb\xbf" + gerar().replace("\n", "\r\n").encode("utf-8"))
