"""Interface simples: cola a URL, dá um nome, escolhe a pasta e clica em Processar."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from processador import (ARQUIVO_ERROS, BASE, Opcoes, atualizar_ytdlp, detectar_plataforma,
                         limpar_temp_antigo, processar, registrar_erro)

APP_DIR = BASE  # funciona tanto no script quanto no .exe
CONFIG = APP_DIR / "config.json"
HISTORICO = APP_DIR / "historico.json"


def ler_json(caminho: Path, padrao):
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except Exception:
        return padrao


def salvar_json(caminho: Path, dados) -> None:
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def abrir_pasta(caminho: str) -> None:
    if not Path(caminho).exists():
        messagebox.showwarning("Pasta não existe", f"A pasta foi movida ou apagada:\n{caminho}")
        return
    if os.name == "nt":
        os.startfile(caminho)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", caminho])
    else:
        subprocess.run(["xdg-open", caminho])


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Análise de Vídeo — extrai imagens + transcrição")
        self.geometry("840x720")
        self.minsize(700, 520)

        self.config_dados = ler_json(CONFIG, {})
        self.historico: list[dict] = ler_json(HISTORICO, [])
        self.fila: queue.Queue = queue.Queue()
        self.rodando = False

        self._montar()
        self._atualizar_historico()
        self.after(100, self._ler_fila)

        # Ao abrir: apaga sobras de vídeo (se o PC desligou no meio) e atualiza o baixador
        limpar_temp_antigo()
        threading.Thread(target=atualizar_ytdlp, args=(lambda m: self.fila.put(("log", m)),),
                         daemon=True).start()

    # ------------------------------------------------------------ tela
    def _montar(self) -> None:
        p = {"padx": 8, "pady": 4}
        topo = ttk.Frame(self, padding=10)
        topo.pack(fill="x")
        topo.columnconfigure(1, weight=1)

        ttk.Label(topo, text="URL do vídeo:").grid(row=0, column=0, sticky="w", **p)
        self.url = tk.StringVar()
        ent = ttk.Entry(topo, textvariable=self.url)
        ent.grid(row=0, column=1, columnspan=2, sticky="ew", **p)
        ent.focus()
        self.lbl_plat = ttk.Label(topo, text="Instagram, TikTok, YouTube, X ou Facebook", foreground="gray")
        self.lbl_plat.grid(row=1, column=1, columnspan=2, sticky="w", padx=8)
        self.url.trace_add("write", lambda *_: self._mostrar_plataforma())

        ttk.Label(topo, text="Nome:").grid(row=2, column=0, sticky="w", **p)
        self.nome = tk.StringVar()
        ttk.Entry(topo, textvariable=self.nome).grid(row=2, column=1, sticky="ew", **p)
        ttk.Label(topo, text="ex.: video estudo 1", foreground="gray").grid(row=2, column=2, sticky="w", **p)

        ttk.Label(topo, text="Salvar em:").grid(row=3, column=0, sticky="w", **p)
        self.destino = tk.StringVar(value=self.config_dados.get("destino", str(Path.home() / "Videos" / "analises")))
        ttk.Entry(topo, textvariable=self.destino).grid(row=3, column=1, sticky="ew", **p)
        ttk.Button(topo, text="Escolher...", command=self._escolher_pasta).grid(row=3, column=2, **p)

        # opções
        opc = ttk.LabelFrame(self, text="Opções", padding=8)
        opc.pack(fill="x", padx=10)
        self.detalhe = tk.StringVar(value=self.config_dados.get("detalhe", "normal"))
        self.por_mosaico = tk.StringVar(value=str(self.config_dados.get("por_mosaico", 12)))
        self.modelo = tk.StringVar(value=self.config_dados.get("modelo", "small"))
        self.idioma = tk.StringVar(value=self.config_dados.get("idioma", "auto"))
        self.cookies = tk.StringVar(value=self.config_dados.get("cookies", "nenhum"))
        self.mosaico = tk.BooleanVar(value=self.config_dados.get("mosaico", True))

        # linha 1: imagens
        ttk.Label(opc, text="Detalhe:").grid(row=0, column=0, sticky="w")
        ttk.Combobox(opc, textvariable=self.detalhe, width=8, state="readonly",
                     values=["pouco", "normal", "muito"]).grid(row=0, column=1, padx=6, sticky="w")
        ttk.Label(opc, text="Imagens por mosaico:").grid(row=0, column=2, sticky="w")
        ttk.Combobox(opc, textvariable=self.por_mosaico, width=4, state="readonly",
                     values=["12", "9", "6"]).grid(row=0, column=3, padx=6, sticky="w")
        ttk.Checkbutton(opc, text="Gerar mosaicos", variable=self.mosaico).grid(row=0, column=4, padx=6, sticky="w")

        # linha 2: áudio e login
        ttk.Label(opc, text="Transcrição:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Combobox(opc, textvariable=self.modelo, width=8, state="readonly",
                     values=["tiny", "base", "small", "medium", "large-v3"]).grid(row=1, column=1, padx=6,
                                                                                   sticky="w", pady=(6, 0))
        ttk.Label(opc, text="Idioma:").grid(row=1, column=2, sticky="w", pady=(6, 0))
        ttk.Combobox(opc, textvariable=self.idioma, width=4, state="readonly",
                     values=["auto", "pt", "en", "es"]).grid(row=1, column=3, padx=6, sticky="w", pady=(6, 0))
        ttk.Label(opc, text="Login via:").grid(row=1, column=4, sticky="w", padx=(6, 0), pady=(6, 0))
        ttk.Combobox(opc, textvariable=self.cookies, width=8, state="readonly",
                     values=["nenhum", "firefox", "chrome", "edge", "brave"]).grid(row=1, column=5, padx=6,
                                                                                    sticky="w", pady=(6, 0))
        ttk.Label(opc, foreground="gray", justify="left", text=(
            "Detalhe: quantas imagens tirar conforme a duração (pouco = metade e mais barato, muito = o dobro).\n"
            "Imagens por mosaico: 12 = mais barato; 6 = cada imagem maior e mais nítida.")
        ).grid(row=2, column=0, columnspan=6, sticky="w", pady=(8, 0))

        botoes = ttk.Frame(self)
        botoes.pack(pady=8)
        self.btn = ttk.Button(botoes, text="▶  Processar", command=self._iniciar)
        self.btn.pack(side="left", padx=4)
        ttk.Button(botoes, text="Ver log de erros", command=self._abrir_log).pack(side="left", padx=4)
        self.status = tk.Label(self, text="", font=("Segoe UI", 11, "bold"))
        self.status.pack()
        self.barra = ttk.Progressbar(self, mode="indeterminate")
        self.barra.pack(fill="x", padx=10)

        # log
        self.log = tk.Text(self, height=9, state="disabled", wrap="word", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, padx=10, pady=6)

        # histórico
        hist = ttk.LabelFrame(self, text="Onde os arquivos foram gravados (duplo clique abre a pasta)", padding=6)
        hist.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.tabela = ttk.Treeview(hist, columns=("data", "nome", "pasta"), show="headings", height=6)
        for col, txt, larg in (("data", "Data", 110), ("nome", "Nome", 160), ("pasta", "Pasta", 480)):
            self.tabela.heading(col, text=txt)
            self.tabela.column(col, width=larg, anchor="w")
        self.tabela.pack(side="left", fill="both", expand=True)
        self.tabela.bind("<Double-1>", self._abrir_item)
        sb = ttk.Scrollbar(hist, orient="vertical", command=self.tabela.yview)
        sb.pack(side="right", fill="y")
        self.tabela.configure(yscrollcommand=sb.set)

    def _mostrar_plataforma(self) -> None:
        plat = detectar_plataforma(self.url.get())
        if plat:
            self.lbl_plat.configure(text=f"✔ {plat.capitalize()} detectado", foreground="green")
        elif self.url.get().strip():
            self.lbl_plat.configure(text="✖ URL não reconhecida", foreground="red")
        else:
            self.lbl_plat.configure(text="Instagram, TikTok, YouTube, X ou Facebook", foreground="gray")

    def _mostrar_status(self, texto: str, cor: str) -> None:
        self.status.configure(text=texto, fg=cor)

    def _abrir_log(self) -> None:
        if not ARQUIVO_ERROS.exists():
            messagebox.showinfo("Log de erros", "Nenhum erro registrado até agora.")
            return
        abrir_pasta(str(ARQUIVO_ERROS))

    def _escolher_pasta(self) -> None:
        pasta = filedialog.askdirectory(initialdir=self.destino.get() or str(Path.home()))
        if pasta:
            self.destino.set(pasta)

    def _escrever(self, msg: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _atualizar_historico(self) -> None:
        self.tabela.delete(*self.tabela.get_children())
        for item in reversed(self.historico):
            self.tabela.insert("", "end", values=(item["data"], item["nome"], item["pasta"]))

    def _abrir_item(self, _evento) -> None:
        sel = self.tabela.selection()
        if sel:
            abrir_pasta(self.tabela.item(sel[0], "values")[2])

    # ------------------------------------------------------------ processamento
    def _iniciar(self) -> None:
        if self.rodando:
            return
        url = self.url.get().strip()
        if not detectar_plataforma(url):
            messagebox.showerror("URL inválida", "Cole um link do Instagram, TikTok, YouTube, X ou Facebook.")
            return
        if not self.destino.get().strip():
            messagebox.showerror("Pasta", "Escolha onde salvar.")
            return
        if not self.nome.get().strip():
            messagebox.showerror("Nome", "Escreva um nome para este vídeo (ex.: video estudo 1).")
            return

        self.config_dados.update(destino=self.destino.get(), detalhe=self.detalhe.get(),
                                 por_mosaico=int(self.por_mosaico.get()),
                                 modelo=self.modelo.get(), idioma=self.idioma.get(),
                                 cookies=self.cookies.get(), mosaico=self.mosaico.get())
        salvar_json(CONFIG, self.config_dados)

        opcoes = Opcoes(
            detalhe=self.detalhe.get(),
            por_mosaico=int(self.por_mosaico.get()),
            modelo_whisper=self.modelo.get(),
            idioma=None if self.idioma.get() == "auto" else self.idioma.get(),
            cookies_navegador=None if self.cookies.get() == "nenhum" else self.cookies.get(),
            gerar_mosaico=self.mosaico.get(),
        )
        self.rodando = True
        self.btn.configure(state="disabled")
        self.barra.start(12)
        self._mostrar_status("⏳ Processando... aguarde", "#1f5fbf")
        self._escrever("-" * 60)
        threading.Thread(target=self._trabalho, args=(url, self.nome.get(), self.destino.get(), opcoes),
                         daemon=True).start()

    def _trabalho(self, url, nome, destino, opcoes) -> None:
        passos: list[str] = []

        def log(m: str) -> None:
            passos.append(m)
            self.fila.put(("log", m))

        try:
            r = processar(url, nome, destino, opcoes, log=log)
            self.fila.put(("ok", r))
        except Exception as e:
            try:
                arquivo_log = registrar_erro(e, url, nome, destino, opcoes, passos)
            except Exception:
                arquivo_log = None
            self.fila.put(("erro", (e, arquivo_log)))

    def _ler_fila(self) -> None:
        try:
            while True:
                tipo, dado = self.fila.get_nowait()
                if tipo == "log":
                    self._escrever(dado)
                elif tipo == "ok":
                    self._fim()
                    self._mostrar_status("✅ Concluído!", "#1a8a2e")
                    self.historico.append({"data": datetime.now().strftime("%d/%m/%Y %H:%M"),
                                           "nome": dado.pasta.name, "pasta": str(dado.pasta),
                                           "url": self.url.get().strip()})
                    salvar_json(HISTORICO, self.historico)
                    self._atualizar_historico()
                    self.url.set("")
                    self.nome.set("")
                    if messagebox.askyesno("Pronto!", f"Arquivos salvos em:\n{dado.pasta}\n\nAbrir a pasta?"):
                        abrir_pasta(str(dado.pasta))
                elif tipo == "erro":
                    erro, arquivo_log = dado
                    self._fim()
                    self._mostrar_status("❌ Não deu certo — tente de novo", "#c62828")
                    self._escrever(f"❌ Erro: {erro}")
                    onde = f"\n\nOs detalhes foram salvos em:\n{arquivo_log}" if arquivo_log else ""
                    if arquivo_log:
                        self._escrever(f"📄 Detalhes do erro salvos em: {arquivo_log}")
                    messagebox.showerror("Não deu certo",
                                         "O vídeo NÃO foi processado. Tente de novo.\n\n"
                                         f"Motivo: {self._explicar_erro(erro)}{onde}")
        except queue.Empty:
            pass
        self.after(100, self._ler_fila)

    def _fim(self) -> None:
        self.rodando = False
        self.barra.stop()
        self.btn.configure(state="normal")

    @staticmethod
    def _explicar_erro(e: Exception) -> str:
        msg = str(e)
        baixo = msg.lower()
        if "login" in baixo or "cookies" in baixo or "rate-limit" in baixo or "private" in baixo:
            return (msg + "\n\nDica: esse post pede login. Em 'Login via', escolha o navegador "
                    "onde você está logado na rede social (Firefox funciona melhor) e tente de novo.")
        if "unsupported url" in baixo:
            return msg + "\n\nO link não parece ser de um vídeo. Confira se copiou o link do post."
        return msg


if __name__ == "__main__":
    App().mainloop()
