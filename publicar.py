"""
Publica uma versão do app Android ou do firmware do STD_MakimaCAN.

Este repositório (público) só guarda os arquivos prontos e a lista de versões
(versoes.json). O código-fonte fica nos repositórios privados.

Uso:
  python publicar.py app       --notas "O que mudou" ["Outra linha" ...] [--seco]
  python publicar.py firmware  --notas "O que mudou" ... [--seco]
  python publicar.py recomendar app|firmware <versao>      # marca a versão "recomendada"
  python publicar.py retirar    app|firmware <versao>      # tira da lista (o arquivo fica no GitHub)

  --substituir  republica uma versão que já está na lista (troca os arquivos).

  --seco   mostra o que faria, sem enviar nada.

O que o script faz (app):
  1. pega o APK de release já compilado (gradlew assembleRelease);
  2. confere pacote, versão e — principalmente — a CHAVE de assinatura: se não for
     a chave de publicação, recusa (uma atualização com outra chave não instala);
  3. calcula SHA-256 e tamanho; cria o release "app-v<versao>" no GitHub com o APK
     (versões beta saem como "pre-release");
  4. acrescenta a versão em versoes.json, faz commit e push.
Firmware: igual, com bootloader.bin, partitions.bin e firmware.bin e os
endereços tirados do flasher_args.json do build (gravados nessa ordem pelo app).

Precisa: Python 3.9+, gh (GitHub CLI) logado, git, Android SDK (apksigner/aapt2).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
APPS = os.path.dirname(AQUI)
REPO_GH = "denisnjn/STD_MakimaCAN-atualizacoes"
URL_BASE = f"https://github.com/{REPO_GH}/releases/download"
LISTA = os.path.join(AQUI, "versoes.json")

PACOTE = "com.makimacan.std"
# Impressão digital da chave de publicação (C:\Users\Denis\STD_MakimaCAN-assinatura).
CERT_SHA256 = "8AC7F1446978F843CE30FD3BE96D797D079C544DF500E25BE21B4A9B9B4E3F66"

APK = os.path.join(APPS, "Android", "MakimacanSTD", "app", "build", "outputs", "apk", "release", "app-release.apk")
FW_REPO = os.path.join(APPS, "idf", "MakimacanSTD_firmware")
FW_BUILD = os.path.join(FW_REPO, ".pio", "build", "makimacan20-esp32")
FW_VERSAO_H = os.path.join(FW_REPO, "src", "app_version.h")
PLACA = "makimacan20-esp32"

RE_VERSAO = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-beta\.(\d+))?$")


def falha(msg: str) -> None:
    print("ERRO:", msg)
    sys.exit(1)


def canal(versao: str) -> str:
    return "beta" if "-beta." in versao else "estavel"


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for bloco in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def ambiente() -> dict:
    """apksigner precisa de Java: usa o JAVA_HOME, ou o JDK 21 instalado para o Android."""
    env = dict(os.environ)
    if not env.get("JAVA_HOME"):
        jdk = os.path.join(env.get("LOCALAPPDATA", ""), "Programs", "MicrosoftJDK21")
        if os.path.isdir(jdk):
            env["JAVA_HOME"] = jdk
    return env


def roda(cmd: list[str], seco: bool = False, **kw) -> str:
    print("  $", " ".join(cmd))
    if seco:
        return ""
    r = subprocess.run(cmd, capture_output=True, text=True, env=ambiente(), **kw)
    if r.returncode != 0:
        falha(f"comando falhou ({r.returncode}):\n{r.stdout}\n{r.stderr}")
    return r.stdout


def ferramenta_sdk(nome: str) -> str:
    sdk = os.environ.get("ANDROID_HOME") or os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk")
    bt = os.path.join(sdk, "build-tools")
    if not os.path.isdir(bt):
        falha(f"Android SDK não encontrado em {sdk}")
    for ver in sorted(os.listdir(bt), reverse=True):
        for ext in (".bat", ".exe", ""):
            p = os.path.join(bt, ver, nome + ext)
            if os.path.isfile(p):
                return p
    falha(f"{nome} não encontrado no build-tools")
    return ""


def gh() -> str:
    p = shutil.which("gh") or r"C:\Program Files\GitHub CLI\gh.exe"
    if not os.path.isfile(p) and not shutil.which("gh"):
        falha("gh (GitHub CLI) não encontrado")
    return p


def carrega_lista() -> dict:
    with open(LISTA, encoding="utf-8") as fh:
        return json.load(fh)


def salva_lista(lista: dict) -> None:
    lista["atualizado_em"] = dt.date.today().isoformat()
    with open(LISTA, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(lista, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def envia(tag: str, titulo: str, notas: list[str], arquivos: list[str], beta: bool, seco: bool,
          substituir: bool = False) -> None:
    corpo = "\n".join(f"- {n}" for n in notas)
    if substituir:
        roda([gh(), "release", "upload", tag, *arquivos, "--clobber", "--repo", REPO_GH], seco)
        roda([gh(), "release", "edit", tag, "--notes", corpo, "--repo", REPO_GH], seco)
        return
    cmd = [gh(), "release", "create", tag, *arquivos, "--repo", REPO_GH, "--title", titulo, "--notes", corpo]
    if beta:
        cmd.append("--prerelease")
    roda(cmd, seco)


def coloca(versoes: list, item: dict, substituir: bool) -> None:
    """Novo vai no topo; republicação troca o item no mesmo lugar."""
    for i, v in enumerate(versoes):
        if v["versao"] == item["versao"]:
            versoes[i] = item
            return
    versoes.insert(0, item)


def commit_lista(msg: str, seco: bool) -> None:
    roda(["git", "-C", AQUI, "add", "versoes.json"], seco)
    roda(["git", "-C", AQUI, "commit", "-m", msg], seco)
    roda(["git", "-C", AQUI, "push"], seco)


# ---------------------------------------------------------------- app

def publica_app(notas: list[str], seco: bool, apk: str = APK, substituir: bool = False) -> None:
    if not os.path.isfile(apk):
        falha(f"APK não encontrado: {apk}\n  rode: gradlew assembleRelease")
    badging = roda([ferramenta_sdk("aapt2"), "dump", "badging", apk])
    m = re.search(r"package: name='([^']+)' versionCode='(\d+)' versionName='([^']+)'", badging)
    if not m:
        falha("não consegui ler pacote/versão do APK")
    pacote, codigo, versao = m.group(1), int(m.group(2)), m.group(3)
    if pacote != PACOTE:
        falha(f"pacote {pacote}, esperado {PACOTE}")
    if not RE_VERSAO.match(versao):
        falha(f"versão fora do padrão: {versao}")

    certs = roda([ferramenta_sdk("apksigner"), "verify", "--print-certs", apk])
    m = re.search(r"certificate SHA-256 digest: ([0-9a-fA-F]+)", certs)
    if not m or m.group(1).upper() != CERT_SHA256:
        falha("o APK NÃO está assinado com a chave de publicação.\n"
              "  Confira ~/.gradle/gradle.properties (STD_KEYSTORE_*) e recompile o release.")

    lista = carrega_lista()
    existe = any(v["versao"] == versao for v in lista["app"]["versoes"])
    if existe and not substituir:
        falha(f"app {versao} já publicado (suba a versão no app/build.gradle.kts, ou use --substituir)")

    nome = f"STD_MakimaCAN-{versao}.apk"
    tag = f"app-v{versao}"
    with tempfile.TemporaryDirectory() as tmp:
        dest = os.path.join(tmp, nome)
        shutil.copyfile(apk, dest)
        item = {
            "versao": versao,
            "codigo": codigo,
            "canal": canal(versao),
            "data": dt.date.today().isoformat(),
            "arquivo": nome,
            "url": f"{URL_BASE}/{tag}/{nome}",
            "sha256": sha256(dest),
            "tamanho": os.path.getsize(dest),
        }
        print(f"app {versao} (código {codigo}, {item['canal']}) — {item['tamanho']} bytes")
        envia(tag, f"App STD_MakimaCAN {versao}", notas, [dest], canal(versao) == "beta", seco, existe)
    coloca(lista["app"]["versoes"], item, existe)
    if not seco:
        salva_lista(lista)
    commit_lista(f"app {versao}" + (" (republicado)" if existe else ""), seco)


# ---------------------------------------------------------------- firmware

def publica_firmware(notas: list[str], seco: bool, substituir: bool = False) -> None:
    with open(FW_VERSAO_H, encoding="utf-8") as fh:
        m = re.search(r'#define\s+FIRMWARE_VERSION\s+"([^"]+)"', fh.read())
    if not m:
        falha("FIRMWARE_VERSION não encontrado em app_version.h")
    versao = m.group(1)
    if not RE_VERSAO.match(versao):
        falha(f"versão fora do padrão: {versao}")

    with open(os.path.join(FW_BUILD, "flasher_args.json"), encoding="utf-8") as fh:
        flasher = json.load(fh)
    # Endereços do flasher_args (ESP-IDF); os arquivos o PlatformIO grava com
    # estes nomes. A área de dados (NVS) não é tocada — presets e AUTOCFG ficam.
    partes_src = sorted([
        (int(flasher["bootloader"]["offset"], 16), "bootloader.bin", "bootloader"),
        (int(flasher["partition-table"]["offset"], 16), "partitions.bin", "particoes"),
        (int(flasher["app"]["offset"], 16), "firmware.bin", "programa"),
    ])
    app_bin = os.path.join(FW_BUILD, "firmware.bin")
    with open(app_bin, "rb") as fh:
        if versao.encode() not in fh.read():
            falha(f"firmware.bin não contém a versão {versao}: recompile o firmware")

    lista = carrega_lista()
    existe = any(v["versao"] == versao for v in lista["firmware"]["versoes"])
    if existe and not substituir:
        falha(f"firmware {versao} já publicado (suba FIRMWARE_VERSION em src/app_version.h, ou use --substituir)")

    tag = f"fw-v{versao}"
    partes = []
    with tempfile.TemporaryDirectory() as tmp:
        enviar = []
        for ender, base, rotulo in partes_src:
            origem = os.path.join(FW_BUILD, base)
            if not os.path.isfile(origem):
                falha(f"não encontrado: {origem} (recompile o firmware)")
            nome = f"STD_MakimaCAN-fw-{versao}-{rotulo}.bin"
            dest = os.path.join(tmp, nome)
            shutil.copyfile(origem, dest)
            enviar.append(dest)
            partes.append({
                "endereco": f"0x{ender:X}",
                "arquivo": nome,
                "url": f"{URL_BASE}/{tag}/{nome}",
                "sha256": sha256(dest),
                "tamanho": os.path.getsize(dest),
            })
        item = {
            "versao": versao,
            "canal": canal(versao),
            "data": dt.date.today().isoformat(),
            "placa": PLACA,
            "chip": "ESP32",
            "flash": {
                "modo": flasher.get("flash_settings", {}).get("flash_mode", "dio"),
                "frequencia": flasher.get("flash_settings", {}).get("flash_freq", "40m"),
                "tamanho": flasher.get("flash_settings", {}).get("flash_size", "2MB"),
            },
            "partes": partes,
        }
        print(f"firmware {versao} ({item['canal']}): " + ", ".join(f"{p['endereco']} {p['tamanho']}B" for p in partes))
        envia(tag, f"Firmware STD_MakimaCAN {versao}", notas, enviar, canal(versao) == "beta", seco, existe)
    coloca(lista["firmware"]["versoes"], item, existe)
    if not seco:
        salva_lista(lista)
    commit_lista(f"firmware {versao}" + (" (republicado)" if existe else ""), seco)


def recomenda(componente: str, versao: str, seco: bool) -> None:
    lista = carrega_lista()
    alvo = next((v for v in lista[componente]["versoes"] if v["versao"] == versao), None)
    if alvo is None:
        falha(f"{componente} {versao} não está na lista")
    if alvo["canal"] != "estavel":
        falha("só uma versão estável pode ser a recomendada")
    lista[componente]["recomendada"] = versao
    print(f"{componente}: recomendada = {versao}")
    if not seco:
        salva_lista(lista)
    commit_lista(f"{componente}: recomendada {versao}", seco)


def retira(componente: str, versao: str, seco: bool) -> None:
    lista = carrega_lista()
    antes = len(lista[componente]["versoes"])
    lista[componente]["versoes"] = [v for v in lista[componente]["versoes"] if v["versao"] != versao]
    if len(lista[componente]["versoes"]) == antes:
        falha(f"{componente} {versao} não está na lista")
    if lista[componente].get("recomendada") == versao:
        lista[componente]["recomendada"] = None
    print(f"{componente} {versao} retirada da lista (o release continua no GitHub)")
    if not seco:
        salva_lista(lista)
    commit_lista(f"{componente}: retira {versao}", seco)


def main() -> None:
    ap = argparse.ArgumentParser(description="Publica app/firmware do STD_MakimaCAN")
    ap.add_argument("componente", choices=["app", "firmware", "recomendar", "retirar"])
    ap.add_argument("resto", nargs="*", help="recomendar/retirar: <app|firmware> <versao>")
    ap.add_argument("--notas", nargs="+", default=[], help="o que mudou: vai só para a página do release no GitHub (o app não mostra)")
    ap.add_argument("--seco", action="store_true", help="só mostra o que faria")
    ap.add_argument("--apk", default=APK, help="APK a publicar (padrão: o release do build)")
    ap.add_argument("--substituir", action="store_true", help="republica uma versão já publicada")
    a = ap.parse_args()
    if a.componente in ("recomendar", "retirar"):
        if len(a.resto) != 2 or a.resto[0] not in ("app", "firmware"):
            falha(f"uso: publicar.py {a.componente} app|firmware <versao>")
        (recomenda if a.componente == "recomendar" else retira)(a.resto[0], a.resto[1], a.seco)
        return
    if not a.notas:
        falha("informe --notas com o que mudou")
    if a.componente == "app":
        publica_app(a.notas, a.seco, a.apk, a.substituir)
    else:
        publica_firmware(a.notas, a.seco, a.substituir)


if __name__ == "__main__":
    main()
