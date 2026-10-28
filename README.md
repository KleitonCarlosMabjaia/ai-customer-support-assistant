# 🤖 AI Customer Support Assistant

Assistente de apoio ao cliente para uma loja de tecnologia fictícia (**TechLoja**), construído em Python com a **API do Claude** (Anthropic).

O assistente conversa com o cliente no terminal e:
- responde a **perguntas frequentes** (envios, devoluções, pagamentos...) com base numa base de conhecimento oficial, sem inventar;
- consulta **produtos, preços e stock** numa base de dados **SQLite**, através de *tool use* (o modelo pede a ferramenta e o programa executa-a);
- admite com honestidade quando não sabe e sugere o contacto com a equipa humana.

> Projeto de portefólio, desenvolvido etapa a etapa com foco em perceber cada decisão: tratamento de erros, gestão segura de chaves e testes automatizados.

---

## ✨ Funcionalidades

| | |
|---|---|
| 💬 **Conversa com memória** | o histórico é enviado em cada pedido (a API é *stateless*); `/novo` recomeça a conversa |
| 📄 **Base de conhecimento (FAQ)** | `data/faq.json` é validado ao arrancar e incluído no *system prompt*, delimitado por etiquetas `<faq>` |
| 🛠️ **Tool use** | ferramenta `procurar_produtos` com *schema* estrito; ciclo manual `tool_use` → `tool_result` com limite de rondas |
| 🗄️ **SQLite** | catálogo persistente, pesquisa sem acentos/maiúsculas, consultas parametrizadas |
| 🛡️ **Erros tratados** | erros técnicos da API traduzidos para mensagens claras; detalhes técnicos só no log |
| 🔑 **Chave protegida** | lida do `.env` (fora do Git), nunca aparece em `repr`, logs ou mensagens |
| ✅ **84 testes** | correm sem internet e sem custos, com um cliente da API simulado |

---

## 🏗️ Arquitetura

```
👤 Cliente
   │
   ▼
cli.py ─────────────── interface de terminal, logging, arranque "fail fast"
   │
   ▼
SupportAssistant ───── histórico + ciclo de ferramentas (assistant.py)
   │        └───────► knowledge_base.py ─► data/faq.json
   ▼
API do Claude ──────── decide responder ou pedir uma ferramenta
   │
   ▼ tool_use
ToolExecutor ───────── valida o pedido e executa-o; nunca lança exceções (tools.py)
   │
   ▼
Catalog (Protocol) ─── SQLiteProductCatalog (products_db.py) ─► data/techloja.db
                       ProductCatalog em memória (products.py, usado nos testes)
```

O `ToolExecutor` depende apenas do `Protocol` `Catalog` (métodos `search` e `get_by_sku`). Por isso, a passagem do catálogo em memória para SQLite mudou uma única linha em `cli.py`.

---

## 🚀 Como executar

**Requisitos:** Python 3.10+ e uma chave da API do Claude com créditos.

```bash
# 1. Criar e ativar um ambiente virtual
python -m venv .venv
.venv\Scripts\Activate.ps1        # Windows (PowerShell)
# source .venv/bin/activate       # macOS / Linux

# 2. Instalar as dependências
pip install -r requirements.txt

# 3. Configurar a chave
copy .env.example .env            # Windows  (macOS/Linux: cp .env.example .env)
#    → abrir o .env e colar a chave em ANTHROPIC_API_KEY

# 4. Executar
python -m support_assistant
```

A chave cria-se em [platform.claude.com/settings/keys](https://platform.claude.com/settings/keys). Uma chave pessoal deve ser associada a um workspace (por exemplo, *Default*).

Na primeira execução, a base de dados `data/techloja.db` é criada automaticamente com produtos de exemplo.

### Exemplos de perguntas

| Pergunta | Comportamento esperado |
|---|---|
| "Quanto custa o envio para a Madeira?" | responde a partir das FAQ |
| "Têm portáteis?" | usa a ferramenta `procurar_produtos` |
| "O MacBook Air está disponível?" | indica que está esgotado (stock 0) |
| "Vendem bicicletas?" | diz que a loja não tem esse produto |

---

## ⚙️ Configuração

Todas as definições vêm de variáveis de ambiente (ou do `.env`):

| Variável | Omissão | Descrição |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | **obrigatória** |
| `ASSISTANT_MODEL` | `claude-opus-5-5` | modelo a usar (ex.: `claude-sonnet-5-5`, mais económico) |
| `ASSISTANT_EFFORT` | `medium` | `low`, `medium`, `high`, `xhigh` ou `max` |
| `ASSISTANT_MAX_TOKENS` | `16000` | tamanho máximo de cada resposta |
| `ASSISTANT_TIMEOUT_SECONDS` | `120` | tempo máximo de espera por pedido |
| `ASSISTANT_COMPANY_NAME` | `TechLoja` | nome da loja no *system prompt* |

Os valores são validados ao arrancar: um valor inválido impede o programa de iniciar, com uma mensagem a explicar o problema.

---

## ✅ Testes

```bash
python -m pytest
```

Nenhum teste chama a API real: um `MagicMock` substitui o cliente, o que torna os testes rápidos, gratuitos e determinísticos. Os ficheiros temporários usam o `tmp_path` do pytest. Os testes cobrem, entre outros:
- tradução de cada erro da API (401, 403, 404, 400, 429, 5xx, ligação, *timeout*);
- ciclo de ferramentas, incluindo o limite de rondas;
- validação do `faq.json` (ficheiro em falta, JSON inválido, campos em falta);
- persistência no SQLite e resistência a *SQL injection*.

---

## 🧠 Decisões de design

- **Separar instruções de dados.** As FAQ vão dentro de `<faq>...</faq>` no prompt, e os textos do cliente vão sempre em parâmetros `?` no SQL, nunca concatenados.
- **"Não sei" não é um erro.** Uma pesquisa sem resultados devolve uma lista vazia (`{"produtos": []}`). As exceções ficam reservadas para falhas reais (configuração, rede, base de dados).
- **Fail fast.** A chave, o `faq.json` e a base de dados são verificados ao arrancar, e não a meio de uma conversa.
- **O modelo pede, o programa decide.** O Claude só vê a definição das ferramentas; o `ToolExecutor` recusa ferramentas desconhecidas e entradas inválidas, e um limite de 5 rondas evita ciclos sem fim.
- **Exceções próprias.** `errors.py` define quatro tipos de erro com mensagens para o utilizador, e a interface não depende da biblioteca `anthropic`.
- **Recusas tratadas.** O pedido usa o *fallback* do lado do servidor para recusas por segurança, e o `stop_reason` é sempre verificado antes de ler a resposta.

---

## 📁 Estrutura

```
├── data/
│   └── faq.json               # perguntas frequentes da loja
├── support_assistant/
│   ├── __main__.py            # permite: python -m support_assistant
│   ├── cli.py                 # interface de terminal
│   ├── config.py              # leitura e validação das definições
│   ├── errors.py              # exceções do assistente
│   ├── assistant.py           # conversa com o Claude e ciclo de ferramentas
│   ├── knowledge_base.py      # carregamento das FAQ
│   ├── tools.py               # definição e execução das ferramentas
│   ├── products.py            # Product, Catalog (Protocol), catálogo em memória
│   └── products_db.py         # catálogo SQLite
├── tests/                     # testes automáticos (pytest)
├── NOTAS.md                   # notas de estudo do projeto
├── .env.example               # modelo de configuração (sem segredos)
└── requirements.txt
```

---

## 🔮 Próximos passos

- Mensagens de erro mais específicas (por exemplo, para falta de créditos).
- Ferramenta para consultar o estado de encomendas.
- Interface web.
- Pesquisa por relevância nas FAQ (RAG), se a base de conhecimento crescer.

---

Desenvolvido por **Kleiton** como projeto de aprendizagem.
