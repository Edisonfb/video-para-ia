"""Gera o executável (pasta dist/AnaliseVideo/ + dist/AnaliseVideo-windows.zip).

Usado pelo GERAR_EXE.bat no seu PC e pelo GitHub Actions ao publicar uma versão.
Formato "pasta" (onedir) de propósito: o formato "arquivo único" se descompacta
inteiro na pasta temporária do C: toda vez que abre.
"""

import os
import shutil
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
os.environ["PYINSTALLER_CONFIG_DIR"] = str(RAIZ / ".cache" / "pyinstaller")  # cache no D:, não no C:

import PyInstaller.__main__  # noqa: E402

NOME = "AnaliseVideo"
DIST = RAIZ / "dist"
BUILD = RAIZ / "build"

PyInstaller.__main__.run([
    str(RAIZ / "app.py"),
    "--name", NOME,
    "--onedir",
    "--windowed",                      # sem janela preta de console
    "--noconfirm", "--clean",
    "--distpath", str(DIST),
    "--workpath", str(BUILD),
    "--specpath", str(BUILD),
    # bibliotecas com arquivos extras (DLLs, modelos de VAD, ffmpeg) que precisam ir junto
    "--collect-all", "faster_whisper",
    "--collect-all", "ctranslate2",
    "--collect-all", "imageio_ffmpeg",
    "--collect-all", "onnxruntime",
    "--collect-all", "av",
    "--collect-all", "tokenizers",
    "--hidden-import", "platformdirs",   # exigido pelo pkg_resources ao iniciar o .exe
    # o yt-dlp NÃO vai dentro: o programa baixa o yt-dlp.exe oficial, que se atualiza sozinho
    "--exclude-module", "yt_dlp",
])

pasta_app = DIST / NOME
shutil.copy(RAIZ / "README.md", pasta_app / "LEIA-ME.md")

zip_base = DIST / f"{NOME}-windows"
shutil.make_archive(str(zip_base), "zip", DIST, NOME)
print(f"\nPronto!\n  Programa: {pasta_app / (NOME + '.exe')}\n  Zip p/ GitHub Releases: {zip_base}.zip")
