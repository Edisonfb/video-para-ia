# Análise de Vídeo

Programa que recebe a URL de um vídeo (Instagram, TikTok, YouTube, X ou Facebook) e prepara o material para uma IA analisar **gastando bem menos**:

1. Baixa o vídeo numa **pasta temporária**.
2. Usa o **FFmpeg** para tirar as imagens das trocas de cena, numa quantidade que acompanha a duração do vídeo (sem repetidas).
3. **Transcreve o áudio no seu próprio PC** com o Whisper (sem custo de API).
4. Salva tudo na pasta que você escolher, com o nome que você escrever.
5. **Apaga o vídeo baixado**, sempre, até quando dá erro.

Em vez de mandar o vídeo inteiro pra IA, você manda um texto e algumas imagens pequenas.

## Baixar e usar (Windows)

1. Na aba **Releases** deste repositório, baixe o `AnaliseVideo-windows.zip`.
2. Extraia numa pasta onde você tenha espaço (ex.: `D:\Programas\AnaliseVideo`).
3. Abra o **`AnaliseVideo.exe`**. Não precisa ter Python instalado.

Na primeira vez, o programa baixa sozinho o que falta: o baixador (`yt-dlp.exe`) e, na primeira transcrição, o modelo do Whisper. **Tudo fica dentro da pasta do programa, nada vai para o C:**:

| Pasta | O que tem |
|---|---|
| `modelos\` | Modelo do Whisper (`small` ≈ 460 MB) |
| `bin\` | `yt-dlp.exe`, que se atualiza sozinho ao abrir o programa |
| `temp\` | Vídeo temporário (apagado no fim; sobras são limpas ao abrir) |
| `logs\` | `erros.log` |

Para desinstalar, é só apagar a pasta.

## O que sai na pasta de destino

Você escreve o nome que quiser para cada vídeo. Por exemplo, com o nome `video estudo 1` a pasta `video-estudo-1/` fica assim:

| Arquivo | O que é |
|---|---|
| `video-estudo-1_LEIA-PARA-IA.md` | **Entregue este pra IA**: dados do post, legenda, lista de imagens e transcrição |
| `video-estudo-1_transcricao.txt` | Fala do vídeo com marcação de tempo |
| `video-estudo-1_frame-01_00m00s.jpg` ... | Imagens das cenas (até 768 px de largura) |
| `video-estudo-1_mosaico-01.jpg` ... | As imagens agrupadas em mosaicos de 12, 9 ou 6 (a opção mais barata) |
| `video-estudo-1_info.json` | Metadados (autor, curtidas, views, data) |

## Quantas imagens são tiradas

O vídeo é dividido em "janelas" de tempo e cada janela rende **no máximo 1 imagem**: o momento em que a cena mais mudou (ou o meio da janela, se nada mudou). O começo do vídeo sempre entra. Imagens repetidas são descartadas, então um vídeo parado gera menos imagens.

| Duração do vídeo | 1 imagem a cada (detalhe *normal*) | Exemplo |
|---|---|---|
| até 1 min | 3 s | Reel de 30 s → ~10 imagens |
| até 10 min | 10 s | 5 min → ~30 imagens |
| até 30 min | 20 s | 30 min → ~90 imagens |
| mais de 30 min | 30 s | 1 h → ~120 imagens |

Mesmo um vídeo que muda de cena o tempo todo não passa desses números.

## Opções

- **Detalhe**: *pouco* = janelas com o dobro do tempo (metade das imagens, mais barato); *normal* = tabela acima; *muito* = metade do tempo (o dobro das imagens).
- **Imagens por mosaico**: 12, 9 ou 6. Com 12 sai mais barato; com 6 cada imagem fica maior e mais nítida (bom quando tem texto na tela). Cada mosaico já sai no tamanho máximo que a IA aproveita (1568 px), e custa mais ou menos o mesmo que uma imagem só.
- **Mande pra IA os mosaicos OU as imagens separadas, não os dois** (senão paga duas vezes).
- **Transcrição**: `tiny`/`base` são rápidos; `small` é o equilíbrio; `medium`/`large-v3` são mais precisos, mais lentos e ocupam mais espaço.
- **Login via**: alguns posts exigem estar logado. Escolha o navegador onde você está logado na rede social (o Firefox costuma funcionar melhor; o Chrome no Windows às vezes bloqueia a leitura dos cookies).

## Quando dá erro

- A tela mostra em vermelho **"Não deu certo — tente de novo"** e uma janela explica o motivo.
- O erro fica salvo em `logs\erros.log` (botão **Ver log de erros**), com data, URL, opções, os passos feitos até o erro e o detalhe técnico. Dá pra entregar esse arquivo pra uma IA descobrir o que aconteceu.
- O vídeo temporário é apagado mesmo quando dá erro.

Problemas comuns:
- **"login required" / "empty media response"** no Instagram → use a opção *Login via*.
- **Parou de baixar de uma rede** → feche e abra o programa (ele atualiza o baixador ao abrir).

---

## Para desenvolvedores

### Rodar pelo código

```bat
INSTALAR.bat     :: cria o .venv e instala as dependências (cache do pip fica em .cache\)
ABRIR.bat        :: abre o programa
```

Pela linha de comando:

```bash
python processador.py "https://www.instagram.com/reel/XXXX/" --nome "video estudo 1" --destino "D:/Videos/analises"
```

### Gerar o executável

```bat
GERAR_EXE.bat
```

Gera `dist\AnaliseVideo\AnaliseVideo.exe` e `dist\AnaliseVideo-windows.zip`. O formato é "pasta" (onedir) de propósito: o formato "arquivo único" se descompacta inteiro na pasta temporária do C: toda vez que abre.

### Publicar uma versão no GitHub

1. Rode o `GERAR_EXE.bat`.
2. No GitHub: **Releases → Draft a new release**, crie a tag (ex.: `v1.1.0`) e arraste o `dist\AnaliseVideo-windows.zip`.
3. O `.exe` nunca vai para o código (está no `.gitignore`), só na Release.

---

Use só com vídeos que você tem direito de baixar e analisar, respeitando os termos de cada plataforma.
