# STD_MakimaCAN — atualizações

Downloads do app Android e do firmware do **STD_MakimaCAN**. O app consulta
`versoes.json` deste repositório ao abrir e mostra, na tela **Atualizações**,
o que há de novo. Nada é instalado sem o usuário tocar em "Instalar"/"Gravar".

Este repositório só tem os arquivos prontos — o código-fonte é privado.

## Segurança

- **App:** o Android só instala uma atualização assinada com a mesma chave do
  app já instalado. Um APK de outra origem não instala por cima.
- **Todos os arquivos:** o app confere o SHA-256 listado em `versoes.json`
  antes de usar o arquivo.

## Canais

| Canal | Significado |
|---|---|
| `estavel` | Testada em bancada. A "recomendada" é a que o app sugere. |
| `beta` | Para teste. O app mostra o selo **BETA**. |

Versões: `M.m.p` (estável) e `M.m.p-beta.N` (beta), ex.: `1.0.0-beta.1` → `1.0.0`.

## `versoes.json` (formato 1)

```jsonc
{
  "formato": 1,
  "app": {
    "pacote": "com.makimacan.std",
    "recomendada": "1.0.0",            // estável sugerida (null = a estável mais nova)
    "versoes": [ {                     // mais nova primeiro
      "versao": "1.0.0", "codigo": 2000000, "canal": "estavel", "data": "2026-10-10",
      "arquivo": "...apk", "url": "...", "sha256": "...", "tamanho": 0
    } ]
  },
  "firmware": {
    "placa": "makimacan20-esp32",
    "recomendada": null,
    "versoes": [ {
      "versao": "1.0.0", "canal": "estavel", "data": "...",
      "placa": "makimacan20-esp32", "chip": "ESP32",
      "flash": { "modo": "dio", "frequencia": "40m", "tamanho": "2MB" },
      "partes": [ { "endereco": "0x1000", "arquivo": "...", "url": "...", "sha256": "...", "tamanho": 0 } ]
    } ]
  }
}
```

O firmware é gravado nas partes listadas (bootloader, partições e programa).
A área de dados do dispositivo (presets, configuração automática) não é apagada.

## Publicar (manutenção)

```
python publicar.py app
python publicar.py firmware
python publicar.py recomendar app 1.0.0
```

Use `--seco` para ver o que seria feito sem enviar nada.

Sem notas de versão: o app e a página do release mostram só a versão, a data
e os selos (recomendada, beta, instalada). O que mudou em cada versão fica no
`CHANGELOG.md` do código-fonte.
