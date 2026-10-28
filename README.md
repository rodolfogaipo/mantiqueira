# Mantiqueira

Assistente pessoal de voz, 100% offline, para Windows 11.

- Conversa por voz ("Mantiqueira…" ou Ctrl+Espaço) e por texto
- Lembretes falados, com repetição (todo dia, toda semana, dias úteis)
- Registra programas e arquivos em uso e responde sobre o que foi feito
- Percebe pendências (arquivos não salvos, reabertos várias vezes)
- Lê o texto da tela quando pedido
- Voz natural (XTTS-v2) com opção de voz personalizada, e voz rápida de reserva (Piper)
- IA local (Qwen 2.5 via llama.cpp) com modo Normal e Turbo

## Como obter o programa

A cada envio para `main`, o GitHub monta o programa automaticamente (aba **Actions**, cerca de 1 hora)
e publica os arquivos na aba **Releases**. Veja `LEIA-ME.txt` para instalar.

## Estrutura

```
app/            programa (Python) e telas (HTML)
build/          receita de montagem: bibliotecas, downloads, empacotamento, instalador
.github/        automação de montagem
```
