"""
Núcleo do programa: baixa o vídeo numa pasta TEMPORÁRIA, extrai frames e áudio
com FFmpeg, transcreve o áudio localmente (Whisper, sem custo de API), grava
tudo na pasta escolhida e APAGA o vídeo baixado.

Pode ser usado sem interface:
    python processador.py "https://www.instagram.com/reel/XXXX/" --nome "video estudo 1" --destino "D:/Videos"
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

Log = Callable[[str], None]


# ----------------------------------------------------------------- pastas
# TUDO fica dentro da pasta do programa (nada vai para o C:):
#   modelos/  -> modelo do Whisper        temp/ -> vídeo temporário (apagado no fim)
#   bin/      -> yt-dlp.exe (baixador)    logs/ -> erros.log

def pasta_base() -> Path:
    if getattr(sys, "frozen", False):           # rodando como .exe
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent      # rodando como script


BASE = pasta_base()
PASTA_MODELOS = BASE / "modelos"
PASTA_TEMP = BASE / "temp"
PASTA_BIN = BASE / "bin"
PASTA_LOGS = BASE / "logs"
ARQUIVO_ERROS = PASTA_LOGS / "erros.log"
PREFIXO_TMP = "analise-video-"


def preparar_ambiente() -> None:
    for pasta in (PASTA_MODELOS, PASTA_TEMP, PASTA_BIN):
        pasta.mkdir(parents=True, exist_ok=True)
    # Qualquer arquivo temporário (nosso, do yt-dlp ou de bibliotecas) vai pra temp/ do programa
    for var in ("TEMP", "TMP", "TMPDIR"):
        os.environ[var] = str(PASTA_TEMP)
    tempfile.tempdir = str(PASTA_TEMP)
    # Cache do Hugging Face (de onde vem o Whisper) também dentro do programa
    os.environ["HF_HOME"] = str(PASTA_MODELOS / "huggingface")
    os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"


def limpar_temp_antigo() -> None:
    """Se o PC desligou no meio de um processamento, o vídeo ficou em temp/. Apaga aqui."""
    for pasta in PASTA_TEMP.glob(PREFIXO_TMP + "*"):
        shutil.rmtree(pasta, ignore_errors=True)


preparar_ambiente()

PLATAFORMAS = {
    "instagram": ("instagram.com", "instagr.am"),
    "tiktok": ("tiktok.com",),
    "youtube": ("youtube.com", "youtu.be"),
    "x": ("x.com", "twitter.com"),
    "facebook": ("facebook.com", "fb.watch", "fb.com"),
}


@dataclass
class Opcoes:
    detalhe: str = "normal"          # pouco / normal / muito -> quantas imagens tirar (ver tamanho_janela)
    por_mosaico: int = 12            # 12 / 9 / 6 imagens por mosaico (menos = cada imagem maior)
    largura_frame: int = 768         # largura das imagens em px (menor = mais barato)
    sensibilidade_cena: float = 0.30 # 0.1 = pega qualquer mudança, 0.5 = só cortes fortes
    modelo_whisper: str = "small"    # tiny / base / small / medium / large-v3
    idioma: Optional[str] = None     # None = detecta sozinho; "pt", "en"...
    cookies_navegador: Optional[str] = None  # "firefox", "chrome", "edge"... (posts que pedem login)
    gerar_mosaico: bool = True       # junta as imagens em mosaicos (o jeito mais barato p/ IA)


@dataclass
class Resultado:
    pasta: Path
    arquivos: list[Path] = field(default_factory=list)
    titulo: str = ""
    plataforma: str = ""


# ----------------------------------------------------------------- utilidades

def detectar_plataforma(url: str) -> Optional[str]:
    url = url.lower()
    for nome, dominios in PLATAFORMAS.items():
        if any(d in url for d in dominios):
            return nome
    return None


def nome_seguro(texto: str) -> str:
    """'Vídeo Estudo 1' -> 'video-estudo-1' (sem acento/espaço, bom p/ Windows e Git)."""
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    texto = re.sub(r"[^\w\s-]", "", texto).strip().lower()
    texto = re.sub(r"[\s_-]+", "-", texto)
    return texto[:80] or "video"


def caminho_ffmpeg() -> str:
    """Usa o ffmpeg do sistema; se não houver, o que vem junto com o imageio-ffmpeg."""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:  # pragma: no cover
        raise RuntimeError("FFmpeg não encontrado. Rode o INSTALAR.bat de novo.") from e


def rodar(cmd: list[str]) -> subprocess.CompletedProcess:
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", creationflags=flags, env=os.environ.copy())


# ----------------------------------------------------------------- yt-dlp (baixador)
# No Windows usamos o yt-dlp.exe oficial em bin/: ele se atualiza sozinho (-U), então o
# programa continua baixando mesmo quando o Instagram/TikTok mudam alguma coisa.

YTDLP_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
_trava_ytdlp = threading.Lock()


def _baixar_arquivo(url: str, destino: Path) -> None:
    parcial = destino.with_suffix(destino.suffix + ".part")
    with urllib.request.urlopen(url, timeout=60) as resp, parcial.open("wb") as f:
        shutil.copyfileobj(resp, f)
    parcial.replace(destino)


def comando_ytdlp(log: Log = print) -> list[str]:
    if os.name == "nt":
        exe = PASTA_BIN / "yt-dlp.exe"
        with _trava_ytdlp:
            if not exe.exists():
                log("⬇️  Primeira vez: baixando o yt-dlp (o baixador de vídeos)...")
                try:
                    _baixar_arquivo(YTDLP_URL, exe)
                except Exception as e:
                    raise RuntimeError(f"Não consegui baixar o yt-dlp.exe. Confira a internet. ({e})") from e
        return [str(exe)]
    sistema = shutil.which("yt-dlp")
    if sistema:
        return [sistema]
    if not getattr(sys, "frozen", False):
        return [sys.executable, "-m", "yt_dlp"]
    raise RuntimeError("yt-dlp não encontrado. Instale com: pip install yt-dlp")


def atualizar_ytdlp(log: Log = print) -> None:
    """Chamado ao abrir o programa. Só o .exe do Windows se autoatualiza."""
    try:
        cmd = comando_ytdlp(log)
        if not cmd[0].lower().endswith(".exe"):
            return
        with _trava_ytdlp:
            r = rodar(cmd + ["-U"])
        texto = (r.stdout + r.stderr).lower()
        if "updated yt-dlp to" in texto:
            log("🔄 Baixador atualizado para a versão mais nova.")
        elif "up to date" in texto or "is up to date" in texto:
            log("✔ Baixador já está na versão mais nova.")
    except Exception as e:
        log(f"⚠️  Não consegui verificar atualização do baixador: {e}")


def versao_ytdlp() -> str:
    try:
        exe = PASTA_BIN / "yt-dlp.exe"
        if os.name == "nt" and not exe.exists():
            return "não instalado"
        return rodar(comando_ytdlp(lambda _: None) + ["--version"]).stdout.strip() or "?"
    except Exception:
        return "?"


def segundos_fmt(s: float) -> str:
    s = int(round(s))
    return f"{s // 60:02d}m{s % 60:02d}s"


def duracao_video(ffmpeg: str, video: Path) -> float:
    saida = rodar([ffmpeg, "-hide_banner", "-i", str(video)]).stderr
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", saida)
    if not m:
        return 0.0
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def tem_audio(ffmpeg: str, video: Path) -> bool:
    return "Audio:" in rodar([ffmpeg, "-hide_banner", "-i", str(video)]).stderr


def pasta_unica(base: Path) -> Path:
    if not base.exists():
        return base
    i = 2
    while Path(f"{base}-{i}").exists():
        i += 1
    return Path(f"{base}-{i}")


def apagar_temporario(pasta: Path, log: Log) -> None:
    """Apaga a pasta temporária com o vídeo. Tenta algumas vezes porque o Windows
    às vezes segura o arquivo aberto por um instante."""
    for tentativa in range(5):
        shutil.rmtree(pasta, ignore_errors=True)
        if not pasta.exists():
            log("🗑️  Vídeo temporário apagado.")
            return
        time.sleep(1 + tentativa)
    log(f"⚠️  Não consegui apagar a pasta temporária: {pasta} — apague manualmente.")


# ----------------------------------------------------------------- etapas

def baixar(url: str, pasta_tmp: Path, opcoes: Opcoes, log: Log) -> tuple[Path, dict]:
    cmd = comando_ytdlp(log)
    log("⬇️  Baixando o vídeo (pasta temporária)...")
    cmd += [
        url,
        "-o", str(pasta_tmp / "video.%(ext)s"),
        "-f", "bv*[height<=720]+ba/b[height<=720]/bv*+ba/b",  # 720p basta p/ análise
        "--merge-output-format", "mp4",
        "--ffmpeg-location", caminho_ffmpeg(),
        "--playlist-items", "1",                  # carrossel: pega o primeiro vídeo
        "--write-info-json", "--no-write-playlist-metafiles",
        "--no-progress", "--no-warnings", "--encoding", "utf-8",
    ]
    if opcoes.cookies_navegador:
        cmd += ["--cookies-from-browser", opcoes.cookies_navegador]

    r = rodar(cmd)
    if r.returncode != 0:
        linhas = [l.strip() for l in r.stderr.splitlines() if l.strip()]
        erros = [l for l in linhas if "ERROR" in l] or linhas[-3:]
        raise RuntimeError("\n".join(erros) or "O download falhou sem mensagem de erro.")

    infos = sorted(pasta_tmp.glob("*.info.json"))
    info = json.loads(infos[0].read_text(encoding="utf-8")) if infos else {}
    videos = [p for p in pasta_tmp.iterdir()
              if p.name.startswith("video.") and p.suffix not in (".json", ".part")]
    if not videos:
        raise RuntimeError("O download terminou mas nenhum vídeo foi encontrado (o post pode ser só foto).")
    video = max(videos, key=lambda p: p.stat().st_size)
    log(f"✅ Baixado: {info.get('title') or 'sem título'} ({video.stat().st_size / 1e6:.1f} MB)")
    return video, info


def remover_repetidas(candidatos: list[tuple[Path, float]], limite: float = 6.0) -> list[tuple[Path, float]]:
    """Descarta imagens quase iguais à última mantida (imagem repetida = custo à toa na IA)."""
    try:
        from PIL import Image, ImageChops, ImageStat
    except ImportError:
        return candidatos
    mantidas, ultima = [], None
    for arq, t in candidatos:
        mini = Image.open(arq).convert("RGB").resize((32, 32))
        if ultima is not None and max(ImageStat.Stat(ImageChops.difference(mini, ultima)).mean) < limite:
            arq.unlink(missing_ok=True)
            continue
        mantidas.append((arq, t))
        ultima = mini
    return mantidas


# Regra de quantas imagens tirar: o vídeo é dividido em "janelas" de tempo e cada
# janela rende no máximo 1 imagem. A janela cresce com a duração do vídeo.
#   até 1 min -> 1 a cada 3 s | até 10 min -> 10 s | até 30 min -> 20 s | mais -> 30 s
# Nível de detalhe: "pouco" = janela 2x maior (metade das imagens), "muito" = metade (o dobro).
FATOR_DETALHE = {"pouco": 2.0, "normal": 1.0, "muito": 0.5}


def tamanho_janela(duracao: float, detalhe: str = "normal") -> float:
    if duracao <= 60:
        base = 3
    elif duracao <= 600:
        base = 10
    elif duracao <= 1800:
        base = 20
    else:
        base = 30
    return base * FATOR_DETALHE.get(detalhe, 1.0)


def detectar_cenas(ffmpeg: str, video: Path) -> list[tuple[float, float]]:
    """Retorna [(tempo, intensidade_da_mudança)] de cada troca de cena do vídeo.
    Analisa uma versão pequena (160 px, 5 quadros/s) pra ser rápido."""
    filtro = "fps=5,scale=160:-2,select='gt(scene\\,0.08)',metadata=print:file=-"
    r = rodar([ffmpeg, "-hide_banner", "-nostats", "-i", str(video), "-an", "-vf", filtro, "-f", "null", "-"])
    cenas, tempo = [], None
    for linha in r.stdout.splitlines():
        m = re.search(r"pts_time:([\d.]+)", linha)
        if m:
            tempo = float(m.group(1))
            continue
        m = re.search(r"lavfi\.scene_score=([\d.]+)", linha)
        if m and tempo is not None:
            cenas.append((tempo, float(m.group(1))))
    return cenas


def extrair_frames(video: Path, destino: Path, nome: str, opcoes: Opcoes, log: Log) -> list[tuple[Path, float]]:
    ffmpeg = caminho_ffmpeg()
    duracao = duracao_video(ffmpeg, video)
    janela = tamanho_janela(duracao, opcoes.detalhe)
    n_janelas = max(1, int(-(-duracao // janela))) if duracao > 0 else 1
    log(f"🎞️  Procurando as cenas (duração {segundos_fmt(duracao)}, 1 imagem a cada até {janela:g}s, "
        f"detalhe '{opcoes.detalhe}')...")

    cenas = detectar_cenas(ffmpeg, video)

    # Escolhe 1 momento por janela: a maior troca de cena dela; se não houve troca, o meio da janela
    # O começo do vídeo (o "gancho") entra sempre; se for igual à próxima, a repetida é descartada
    tempos: list[float] = [min(0.3, duracao / 2) if duracao else 0.0]
    for k in range(n_janelas):
        ini, fim = k * janela, min((k + 1) * janela, duracao or janela)
        trocas = [(t, s) for t, s in cenas if ini <= t < fim and s >= opcoes.sensibilidade_cena]
        if trocas:
            t = max(trocas, key=lambda x: x[1])[0] + 0.3   # um instante depois do corte: imagem nítida
        elif k == 0:
            continue                                        # 1ª janela sem corte: o começo já cobre
        else:
            t = (ini + fim) / 2
        tempos.append(min(t, max(0.0, (duracao or t) - 0.1)))
    tempos = sorted(set(round(t, 2) for t in tempos))

    tmp = destino / "_frames_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    escala = f"scale='min({opcoes.largura_frame},iw)':-2"
    candidatos: list[tuple[Path, float]] = []
    for i, t in enumerate(tempos):
        arq = tmp / f"f_{i:05d}.jpg"
        rodar([ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(video),
               "-frames:v", "1", "-vf", escala, "-q:v", "3", str(arq)])
        if arq.exists():
            candidatos.append((arq, t))

    candidatos = remover_repetidas(candidatos)

    finais: list[tuple[Path, float]] = []
    digitos = max(2, len(str(len(candidatos))))
    for i, (arq, t) in enumerate(candidatos, 1):
        novo = destino / f"{nome}_frame-{i:0{digitos}d}_{segundos_fmt(t)}.jpg"
        shutil.move(str(arq), novo)
        finais.append((novo, t))
    shutil.rmtree(tmp, ignore_errors=True)
    log(f"✅ {len(finais)} imagens salvas (repetidas descartadas).")
    return finais


# Grades do mosaico conforme a quantidade por mosaico e o formato do vídeo
GRADES = {
    "em_pe": {12: (4, 3), 9: (3, 3), 6: (3, 2)},     # (colunas, linhas) p/ vídeo vertical
    "deitado": {12: (3, 4), 9: (3, 3), 6: (2, 3)},   # p/ vídeo horizontal
}
LADO_MAX_IA = 1568  # a IA reduz imagens maiores que isso; gerar maior é desperdício


def gerar_mosaicos(frames: list[tuple[Path, float]], destino: Path, nome: str,
                   por_mosaico: int, log: Log) -> list[tuple[Path, int, int]]:
    """Divide as imagens em mosaicos de `por_mosaico` (12, 9 ou 6).
    Retorna [(arquivo, nº da 1ª imagem, nº da última)]."""
    if not frames:
        return []
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return []
    try:
        fonte = ImageFont.load_default(size=16)
    except TypeError:  # Pillow antigo
        fonte = ImageFont.load_default()

    with Image.open(frames[0][0]) as im0:
        proporcao = im0.height / im0.width
    formato = "em_pe" if proporcao > 1 else "deitado"
    por_mosaico = por_mosaico if por_mosaico in GRADES[formato] else 12
    colunas, linhas = GRADES[formato][por_mosaico]
    # tamanho de cada quadrinho p/ o mosaico inteiro caber em LADO_MAX_IA
    larg = int(min(LADO_MAX_IA / colunas, LADO_MAX_IA / (linhas * proporcao)))
    alt = int(larg * proporcao)

    total = -(-len(frames) // por_mosaico)
    saida = []
    for m in range(total):
        grupo = frames[m * por_mosaico:(m + 1) * por_mosaico]
        usadas_linhas = -(-len(grupo) // colunas)
        mosaico = Image.new("RGB", (colunas * larg, usadas_linhas * alt), "black")
        desenho = ImageDraw.Draw(mosaico)
        for j, (arq, t) in enumerate(grupo):
            numero = m * por_mosaico + j + 1
            with Image.open(arq) as im:
                quadro = im.convert("RGB").resize((larg, alt))
            x, y = (j % colunas) * larg, (j // colunas) * alt
            mosaico.paste(quadro, (x, y))
            rotulo = f" {numero} | {segundos_fmt(t)} "
            caixa = desenho.textbbox((x + 4, y + 4), rotulo, font=fonte)
            desenho.rectangle(caixa, fill="black")
            desenho.text((x + 4, y + 4), rotulo, fill="yellow", font=fonte)
        caminho = destino / f"{nome}_mosaico-{m + 1:02d}.jpg"
        mosaico.save(caminho, quality=85)
        saida.append((caminho, m * por_mosaico + 1, m * por_mosaico + len(grupo)))
    log(f"🧩 {len(saida)} mosaico(s) gerado(s), {por_mosaico} imagens em cada.")
    return saida


_modelos_cache: dict = {}


def transcrever(video: Path, pasta_tmp: Path, destino: Path, nome: str, opcoes: Opcoes, log: Log) -> tuple[Optional[Path], str]:
    ffmpeg = caminho_ffmpeg()
    if not tem_audio(ffmpeg, video):
        log("🔇 Vídeo sem áudio — pulando transcrição.")
        return None, ""

    # FFmpeg entrega o áudio já no formato do Whisper (16 kHz, mono) direto na memória
    import numpy as np
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    bruto = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(video),
                            "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                           capture_output=True, creationflags=flags).stdout
    if not bruto:
        log("⚠️  Não consegui extrair o áudio.")
        return None, ""
    audio = np.frombuffer(bruto, np.int16).astype(np.float32) / 32768.0

    log(f"📝 Transcrevendo o áudio no seu PC (modelo '{opcoes.modelo_whisper}')... "
        "na 1ª vez ele baixa o modelo, demora um pouco.")
    from faster_whisper import WhisperModel

    chave = opcoes.modelo_whisper
    if chave not in _modelos_cache:
        # CPU: funciona em qualquer PC (GPU exige drivers CUDA instalados à parte)
        _modelos_cache[chave] = WhisperModel(chave, device="cpu", compute_type="int8",
                                             download_root=str(PASTA_MODELOS))
    modelo = _modelos_cache[chave]

    segmentos, info = modelo.transcribe(audio, language=opcoes.idioma, vad_filter=True)
    linhas, texto_corrido = [], []
    for s in segmentos:
        linhas.append(f"[{segundos_fmt(s.start)} - {segundos_fmt(s.end)}] {s.text.strip()}")
        texto_corrido.append(s.text.strip())

    caminho = destino / f"{nome}_transcricao.txt"
    cabecalho = f"Idioma detectado: {info.language} ({info.language_probability:.0%})\n\n"
    caminho.write_text(cabecalho + "\n".join(linhas) + "\n", encoding="utf-8")
    log(f"✅ Transcrição salva ({len(linhas)} trechos, idioma: {info.language}).")
    return caminho, " ".join(texto_corrido)


def escrever_resumo(destino: Path, nome: str, url: str, plataforma: str, info: dict,
                    frames: list[tuple[Path, float]], mosaicos: list[tuple[Path, int, int]],
                    transcricao: Optional[Path]) -> Path:
    """Um arquivo .md único que você entrega pra IA: metadados + lista de imagens + fala."""
    legenda = (info.get("description") or "").strip()
    linhas = [
        f"# {nome}",
        "",
        "Material extraído automaticamente para análise. Analise as imagens e a transcrição abaixo.",
        "",
        "## Dados do vídeo",
        f"- URL: {url}",
        f"- Plataforma: {plataforma}",
        f"- Autor: {info.get('uploader') or info.get('channel') or '—'}",
        f"- Título: {info.get('title') or '—'}",
        f"- Duração: {segundos_fmt(info.get('duration') or 0)}",
        f"- Curtidas: {info.get('like_count', '—')} | Comentários: {info.get('comment_count', '—')} | Views: {info.get('view_count', '—')}",
        f"- Publicado em: {info.get('upload_date') or '—'}",
        f"- Processado em: {datetime.now():%d/%m/%Y %H:%M}",
        "",
        "## Legenda / descrição do post",
        legenda or "(sem legenda)",
        "",
        "## Imagens",
        "Use os MOSAICOS (mais barato) OU as imagens separadas (mais detalhe), não os dois.",
        "Cada imagem tem um número e o tempo do vídeo em que aparece.",
        "",
    ]
    if mosaicos:
        linhas.append("### Mosaicos")
        linhas += [f"- `{p.name}` — imagens {a} a {b}" for p, a, b in mosaicos]
        linhas.append("")
    linhas.append("### Imagens separadas")
    linhas += [f"- {i}. `{p.name}` — {segundos_fmt(t)}" for i, (p, t) in enumerate(frames, 1)]
    linhas += ["", "## Transcrição do áudio"]
    linhas.append(transcricao.read_text(encoding="utf-8") if transcricao else "(sem áudio)")
    caminho = destino / f"{nome}_LEIA-PARA-IA.md"
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return caminho


# ----------------------------------------------------------------- log de erros

def registrar_erro(erro: BaseException, url: str = "", nome: str = "", destino: str = "",
                   opcoes: Opcoes | None = None, passos: list[str] | None = None) -> Path:
    """Acrescenta o erro em logs/erros.log com tudo que a IA precisa pra entender o que
    aconteceu: quando, qual URL, as opções, o que foi feito até o erro e o traceback."""
    import platform
    import traceback

    PASTA_LOGS.mkdir(exist_ok=True)
    bloco = [
        "=" * 70,
        f"ERRO em {datetime.now():%d/%m/%Y %H:%M:%S}",
        f"URL: {url}",
        f"Plataforma: {detectar_plataforma(url) or 'não reconhecida'}",
        f"Nome: {nome}",
        f"Destino: {destino}",
        f"Opções: {opcoes}",
        f"Sistema: {platform.platform()} | Python {platform.python_version()} | yt-dlp {versao_ytdlp()}",
        "",
        f"Mensagem: {type(erro).__name__}: {erro}",
        "",
        "Passos até o erro:",
        *(f"  {p}" for p in (passos or [])),
        "",
        "Detalhe técnico (traceback):",
        "".join(traceback.format_exception(type(erro), erro, erro.__traceback__)).rstrip(),
        "",
    ]
    with ARQUIVO_ERROS.open("a", encoding="utf-8") as f:
        f.write("\n".join(bloco) + "\n")
    return ARQUIVO_ERROS


# ----------------------------------------------------------------- principal

def processar(url: str, nome: str, pasta_destino: str | Path, opcoes: Opcoes | None = None,
              log: Log = print) -> Resultado:
    opcoes = opcoes or Opcoes()
    url = url.strip()
    plataforma = detectar_plataforma(url)
    if not plataforma:
        raise ValueError("URL não reconhecida. Use Instagram, TikTok, YouTube, X ou Facebook.")

    nome = nome_seguro(nome or f"video-{datetime.now():%Y%m%d-%H%M%S}")
    destino = pasta_unica(Path(pasta_destino) / nome)
    if destino.name != nome:
        nome = destino.name
    destino.mkdir(parents=True, exist_ok=True)
    log(f"📁 Salvando em: {destino}")

    pasta_tmp = Path(tempfile.mkdtemp(prefix=PREFIXO_TMP, dir=PASTA_TEMP))
    try:
        video, info = baixar(url, pasta_tmp, opcoes, log)
        frames = extrair_frames(video, destino, nome, opcoes, log)
        mosaicos = (gerar_mosaicos(frames, destino, nome, opcoes.por_mosaico, log)
                    if opcoes.gerar_mosaico else [])
        transcricao, _ = transcrever(video, pasta_tmp, destino, nome, opcoes, log)
        resumo = escrever_resumo(destino, nome, url, plataforma, info, frames, mosaicos, transcricao)

        dados = {k: info.get(k) for k in ("id", "title", "uploader", "duration", "upload_date",
                                          "like_count", "comment_count", "view_count",
                                          "description", "webpage_url")}
        (destino / f"{nome}_info.json").write_text(json.dumps(dados, ensure_ascii=False, indent=2),
                                                   encoding="utf-8")
    except Exception:
        # Se der erro, não deixa pasta de saída vazia pra trás
        if destino.exists() and not any(destino.iterdir()):
            destino.rmdir()
        raise
    finally:
        apagar_temporario(pasta_tmp, log)  # SEMPRE apaga o vídeo, mesmo com erro

    arquivos = sorted(destino.iterdir())
    log(f"🎉 Pronto! {len(arquivos)} arquivos. Entregue para a IA o arquivo: {resumo.name}")
    return Resultado(pasta=destino, arquivos=arquivos, titulo=info.get("title") or "", plataforma=plataforma)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Extrai imagens + transcrição de um vídeo de rede social.")
    ap.add_argument("url")
    ap.add_argument("--nome", default="")
    ap.add_argument("--destino", default=str(Path.cwd() / "saida"))
    ap.add_argument("--detalhe", choices=["pouco", "normal", "muito"], default="normal")
    ap.add_argument("--por-mosaico", type=int, choices=[12, 9, 6], default=12)
    ap.add_argument("--modelo", default="small")
    ap.add_argument("--idioma", default=None)
    ap.add_argument("--cookies", default=None, help="navegador p/ cookies: firefox, chrome, edge")
    a = ap.parse_args()
    opc = Opcoes(detalhe=a.detalhe, por_mosaico=a.por_mosaico, modelo_whisper=a.modelo, idioma=a.idioma,
                 cookies_navegador=a.cookies)
    passos: list[str] = []

    def log_cli(m: str) -> None:
        passos.append(m)
        print(m)

    try:
        processar(a.url, a.nome, a.destino, opc, log=log_cli)
    except Exception as e:
        arq = registrar_erro(e, a.url, a.nome, a.destino, opc, passos)
        print(f"\n❌ NÃO DEU CERTO: {e}\nTente de novo. Detalhes salvos em: {arq}")
        raise SystemExit(1)
