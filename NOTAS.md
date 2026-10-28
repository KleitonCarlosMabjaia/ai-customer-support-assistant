# 📒 Notas de estudo: AI Customer Support Assistant

Resumo do que fui aprendendo ao construir este projeto, etapa a etapa.

---

## 🗺️ O plano

| Etapa | O que faz | Estado |
|---|---|---|
| 1 | Ligar à API do Claude e conversar no terminal | ✅ Feita |
| 2 | Base de conhecimento com perguntas frequentes (FAQ) | ✅ Feita |
| 3 | "Armazém" de produtos + ferramentas (*tool use*) | ✅ Feita |
| 4 | Trocar o armazém de faz-de-conta por uma base de dados SQLite | ✅ Feita |

Para correr o programa: `python -m support_assistant`
Para correr os testes: `python -m pytest`

---

## Etapa 1: falar com o Claude

### Os ficheiros

| Ficheiro | Para que serve |
|---|---|
| `config.py` | Lê a chave e as definições do `.env` e verifica se estão certas |
| `errors.py` | As nossas exceções (erros com mensagens em português) |
| `assistant.py` | O `SupportAssistant`: guarda a conversa e fala com o Claude |
| `cli.py` | O terminal onde o cliente escreve e lê as respostas |
| `tests/` | Testes automáticos que não gastam dinheiro |

### As ideias principais

**🔑 A chave da API é como a palavra-passe do cartão bancário.**
Quem a tiver pode usar o Claude e quem paga sou eu. Por isso:
- fica no ficheiro `.env`, que só existe no meu computador;
- o `.env` está no `.gitignore` (a lista de coisas que o Git ignora), por isso nunca vai para o GitHub;
- o `.env.example` é um modelo **sem** a chave verdadeira, para outras pessoas saberem o que preencher.

> O código é a porta de casa, que toda a gente vê. A chave fica no bolso, não colada na porta.

**🧠 A API não tem memória.**
Cada pedido é tratado como se fosse o primeiro. Por isso guardamos a conversa numa lista (`self._history`) e enviamos tudo em cada pedido.
- Isto **não é uma base de dados**: é uma lista na memória, que desaparece quando o programa fecha.
- O comando `/novo` limpa a lista e começa uma conversa nova.

> É como entregar ao Claude o caderno com a conversa toda, para ele reler antes de responder.

**🎬 Os testes usam um "duplo de cinema" (`MagicMock`).**
Se os testes chamassem a API verdadeira, custavam dinheiro, precisavam de internet, eram lentos e davam respostas diferentes de cada vez. O `MagicMock` finge ser o cliente da API e responde exatamente o que lhe mandamos.
- Isto só funciona porque o `SupportAssistant` recebe o cliente "de fora" (o parâmetro `client=`). Chama-se **injeção de dependência**.

**🍽️ A função `_send` é o "empregado de mesa".**
A biblioteca `anthropic` tem dezenas de erros técnicos (a "cozinha"). O `_send` traduz-os em 4 erros nossos, com mensagens simples, e o `cli.py` (o "cliente") só precisa de conhecer esses 4.

| Erro nosso | Quando acontece |
|---|---|
| `ConfigurationError` | chave errada, modelo errado, ficheiro estragado → é preciso corrigir a configuração |
| `InvalidQuestionError` | pergunta vazia ou demasiado longa |
| `TemporaryServiceError` | sem internet, demasiados pedidos, servidor em baixo → tentar mais tarde |
| `AssistantAPIError` | outro erro da API |

---

## Etapa 2: as perguntas frequentes (FAQ)

### Os ficheiros

| Ficheiro | Para que serve |
|---|---|
| `data/faq.json` | As perguntas e respostas oficiais da loja |
| `knowledge_base.py` | Lê o `faq.json`, verifica-o e transforma-o em texto |
| `tests/test_knowledge_base.py` | Testes do FAQ |

### As ideias principais

**🧑‍💼 O Claude é um funcionário novo que não sabe nada da loja.**
Damos-lhe uma folha com as perguntas frequentes (o `faq.json`) e a instrução: *"usa só esta folha para questões da loja; se não estiver lá, não inventes"*.

**📄 JSON** é um formato de texto para guardar dados organizados.
- `[ ... ]` é uma **lista**;
- `{ ... }` é um **objeto** (em Python, um **dicionário**), com pares *chave → valor*.

**Porque é que as FAQ ficam num ficheiro à parte?** Para mudar as respostas sem mexer no código. Até quem não sabe programar o consegue fazer, sem perigo de estragar o programa.

**⏰ *Fail fast* (falhar cedo).**
O `faq.json` é verificado **logo ao abrir o programa**. Se estiver estragado (ficheiro em falta, vírgula a mais, entrada sem resposta), o programa avisa e nem arranca.

> Como o cozinheiro que verifica os ingredientes de manhã, antes de abrir o restaurante, e não a meio do jantar.

**📦 As etiquetas `<faq>` e `</faq>` são uma caixa.**
Separam as **respostas da loja** (dentro da caixa) das **instruções** (fora da caixa), para o Claude não as confundir.

**📝 `tmp_path` é uma folha de rascunho.**
Nos testes estragamos ficheiros de propósito. Fazemo-lo numa pasta temporária que o pytest apaga no fim, por isso o `faq.json` verdadeiro (o "caderno da escola") fica intacto.
- Só o teste `test_real_faq_file_is_valid` olha para o ficheiro verdadeiro. Existe para avisar se alguém o estragar.

### ⭐ A lição mais importante: "não sei" ≠ "erro"

| Situação | O que é |
|---|---|
| O cliente pergunta por bicicletas e não está nas FAQ | **Não é erro.** O assistente diz honestamente que não sabe e sugere contactar a equipa |
| O `faq.json` está estragado, não há internet, a chave está errada | **É erro.** Alguma coisa está avariada |

> Um erro (exceção) quer dizer que **algo no sistema está avariado**. Não saber uma resposta é uma situação normal.

**E se houvesse 10 000 FAQ?** Enviá-las todas em cada pedido seria lento, caro e podia não caber (há um limite de texto: a *janela de contexto*). A solução seria procurar só as FAQ parecidas com a pergunta e enviar apenas essas (chama-se **RAG**).

---

## Etapa 3: produtos e ferramentas (*tool use*)

### Os ficheiros

| Ficheiro | Para que serve |
|---|---|
| `products.py` | O "armazém" de faz-de-conta: a lista de produtos e a pesquisa |
| `tools.py` | O "telefone": a etiqueta da ferramenta e o porteiro que atende |
| `tests/test_products.py`, `tests/test_tools.py` | Os testes |

### A ideia geral: o telefone 📞

O Claude está fechado numa sala, sem ver o armazém. Damos-lhe um **telefone** com uma **etiqueta**. Quando um cliente pergunta por um produto:

```
👤 Cliente:  "Têm o portátil Lenovo?"
🤖 Claude:   escreve um bilhete: "liga para procurar_produtos('portátil lenovo')"
🐍 Programa: faz o telefonema (corre a função) e devolve o resultado ao Claude
🤖 Claude:   "Sim! Custa 799 € e temos 5 unidades."
```

- O Claude **não corre** a função: só **pede**. Quem a corre é o nosso programa Python.
- **Porquê assim? Segurança e controlo.** O nosso programa decide o que é permitido. Se alguém tentasse "apaga os produtos todos", não havia nenhum telefone para isso.
- O Claude decide sozinho quando ligar. Para o horário vai à folha de FAQ, não precisa do telefone.

### Parte 1: o armazém (`products.py`)

- **`Product`**: a etiqueta de cada produto, com `sku` (o código, como um código de barras), `name`, `price` e `stock`.
- **`normalize`**: põe o texto em minúsculas e tira os acentos ("Portátil" → "portatil"), para o cliente encontrar o produto mesmo sem acentos ou com maiúsculas.
- **`ProductCatalog.search`**: encontra os produtos cujo nome tem **todas** as palavras pesquisadas (no máximo 5).
- **`ProductCatalog.get_by_sku`**: procura pelo código. Devolve `None` ("nada") se não existir.

**📦 Lista vazia ≠ não haver lista.** `search("bicicleta")` devolve `[]`, uma **caixa vazia**. Quem pediu recebe sempre uma caixa e só tem de olhar lá para dentro.

### Parte 2: o telefone (`tools.py`)

**🏷️ A etiqueta (`SEARCH_PRODUCTS_TOOL`) é TUDO o que o Claude sabe.** Ele nunca vê o código Python.

| Parte | Para que serve |
|---|---|
| `name` | o nome do telefone: `procurar_produtos` |
| `description` | **quando** o deve usar |
| `input_schema` | o **formulário** a preencher (o campo `pesquisa`, obrigatório) |
| `strict: True` | a API garante que o formulário vem bem preenchido |

> Como um telefone com o autocolante "PIZZARIA" 🍕: sabes que se ligares arranjas pizza, mas não vês a cozinha.

**🚪 O porteiro (`ToolExecutor.run`) verifica por ordem:**
1. O telefone pedido existe? Não → bilhete de erro: "essa ferramenta não existe".
2. O formulário vem bem preenchido? Não → bilhete de erro.
3. O armazém avariou? Sim → bilhete de erro: "sistema indisponível". O detalhe técnico vai só para o log.
4. Tudo bem → bilhete com os produtos em JSON.

**Regra de ouro: o `run` nunca rebenta. Devolve SEMPRE um bilhete (`ToolResult`).**
- 💥 *Rebentar* (o programa fecha) → nunca acontece.
- 📝 *Bilhete de erro* (`is_error=True`) → o Claude explica o problema ao cliente e a conversa continua.

| Resposta do armazém | Erro? |
|---|---|
| 🧑‍🍳 "Não temos bicicletas." → `{"produtos": []}` | **Não**, é uma resposta normal |
| 😵 O armazém não responde → "sistema indisponível" | **Sim**, há uma avaria |

### Parte 3: o ciclo (`assistant.py`)

O `ask()` passou a ter um ciclo `while` ("enquanto"):

```
envia a pergunta ao Claude
ENQUANTO o Claude pedir ferramentas (stop_reason == "tool_use"):
    junta à conversa o bilhete do Claude (o pedido)
    junta à conversa os nossos bilhetes de resposta (tool_result)
    envia tudo outra vez ao Claude
mostra a resposta final ao cliente
```

- **`_run_tools`** percorre os pedidos do Claude, chama o porteiro (`ToolExecutor.run`) e escreve um bilhete `tool_result` para cada pedido.
- **`tool_use_id`** é o "número do pedido". Cada resposta leva o número do pedido a que responde, como a senha numa fila, para o Claude saber que resposta é de que pergunta.
- **🛑 Travão de segurança (`MAX_TOOL_ROUNDS = 5`)**: se o Claude pedisse ferramentas sem parar, o ciclo nunca acabava, e cada volta custa dinheiro. Ao fim de 5 voltas paramos e pedimos desculpa ao cliente.
- O parâmetro `tools` só é enviado à API quando há ferramentas.
- Nos testes, o `side_effect = [resposta1, resposta2]` faz o duplo de cinema dar respostas diferentes em cada chamada: primeiro "quero usar o telefone", depois a resposta final.

### Experimentar a sério: a chave e os créditos

- As chaves atuais são **pessoais** (`sk-ant-usr-...`). Ao criar uma, liga-a a um **workspace** (o "Default"). Sem isso, a API recusa a chave.
- A chave **nunca** se cola na conversa, em capturas de ecrã ou no código. Só no `.env`. Se for exposta, apaga-se na consola e cria-se outra.
- Um pedido "gratuito" (a lista de modelos) serve para testar a chave sem gastar créditos.
- Fazer perguntas exige **créditos** (*Billing*). O erro `400 ... credit balance is too low` quer dizer "sem saldo", e `401 invalid x-api-key` quer dizer "chave errada". O `assistant.log` mostrou qual era o problema.

---

## Etapa 4: a base de dados SQLite

### Os ficheiros

| Ficheiro | Para que serve |
|---|---|
| `products_db.py` | O armazém a sério: os produtos guardados no ficheiro `data/techloja.db` |
| `products.py` | Ganhou o `Catalog` (a "forma da ficha") |
| `tests/test_products_db.py` | Os testes da base de dados |

### A ideia principal: a mesa e a gaveta

| | 🪑 Mesa (memória RAM) | 🗄️ Gaveta (disco) |
|---|---|---|
| Exemplos | listas, variáveis, o histórico da conversa | ficheiros: `faq.json`, `.env`, `techloja.db` |
| Ao fechar o programa | **limpa-se** | **fica tudo** |

> Experiência: criei `compras = ["pão", "leite"]` no Python, saí e voltei a entrar. `compras` deu `NameError`, porque a mesa foi limpa.
>
> Atenção: `PS C:\...>` é o PowerShell e `>>>` é o Python. São "línguas" diferentes!

### Tabelas e SQL

- Uma **tabela** é como uma folha de Excel: cada **linha** é um produto e cada **coluna** é uma informação.
- **SQL** é a língua para falar com a base de dados: `SELECT * FROM produtos WHERE sku = ?`.
- Regras que a própria base de dados garante (o "segurança à porta"):
  - `PRIMARY KEY`: o `sku` nunca se repete;
  - `NOT NULL`: a coluna não pode ficar vazia;
  - `CHECK (preco >= 0)`: nada de preços negativos.
- A coluna **`nome_pesquisa`** guarda o nome sem acentos e em minúsculas, para a pesquisa funcionar com "PORTATIL".
- `LIKE '%lenovo%'` quer dizer "contém lenovo".

### 🛡️ SQL injection e a "caixa" `?`

Se colássemos o texto do cliente na frase SQL, um texto como `x' OR '1'='1` fechava a aspa e passava a ser **instrução** (devolvia tudo, ou pior: `DROP TABLE` apagava a tabela).

Com `?`, o texto do cliente vai **à parte, dentro de uma caixa**, e nunca consegue mudar as instruções. É a mesma ideia das etiquetas `<faq>`: **separar instruções de dados**.

> Um `f"..."` na frase SQL só é seguro quando o que entra é texto **nosso** e fixo, nunca texto do cliente.

### Abrir e fechar a gaveta (`_connect`)

- `finally` → a ligação é fechada **sempre**, aconteça o que acontecer (a porta do frigorífico que fecha sozinha).
- `with conn:` → se tudo correr bem, **guarda** (*commit*). Se houver erro a meio, **desfaz tudo** (*rollback*).

### 🔌 A tomada elétrica (`Protocol`)

O `Catalog` descreve a "forma da ficha": ter `search` e `get_by_sku`. O porteiro (`ToolExecutor`) aceita **qualquer** catálogo com essa ficha, seja em memória ou SQLite. Por isso trocámos o armazém **sem mexer** no porteiro, no ciclo ou no Claude: no `cli.py` mudou só **uma linha**.

> Cada peça só conhece os "botões" das outras, não o seu interior. Assim trocam-se peças como no LEGO. 🧱

- O ficheiro `data/techloja.db` é criado automaticamente na primeira execução e está no `.gitignore`.

---

## 📖 Pequeno dicionário

| Palavra | Significado simples |
|---|---|
| **API** | uma forma de um programa falar com outro (o nosso programa fala com o Claude) |
| **Chave da API** | a palavra-passe que prova que o pedido é meu |
| **Prompt de sistema** | as instruções fixas que dizem ao Claude como se comportar |
| **Exceção** | um erro que o Python "lança" quando algo corre mal |
| **Dataclass** | uma caixinha de dados com nomes (`frozen=True` quer dizer que não se pode alterar) |
| **Classe / método** | uma "máquina" e os "botões" que ela tem |
| **Teste automático** | um pequeno programa que verifica se o código faz o que deve |
| **Mock** | um duplo de cinema: um objeto falso que finge ser o verdadeiro |
| **JSON** | formato de texto para guardar dados organizados |
| **Fail fast** | descobrir os problemas o mais cedo possível |
| **Tool use** | dar ferramentas ao Claude, que ele pede e nós executamos |
| **RAG** | procurar só a informação relevante antes de perguntar ao Claude |
| **Base de dados** | uma "gaveta": dados guardados num ficheiro, que não se perdem ao fechar o programa |
| **SQLite** | uma base de dados simples, num só ficheiro, que já vem com o Python |
| **SQL** | a língua para pedir coisas à base de dados (`SELECT`, `INSERT`...) |
| **SQL injection** | um ataque em que texto do cliente se transforma em instruções. Evita-se com `?` |
| **Protocol** | a "forma da ficha": os métodos que uma peça tem de ter para encaixar |
| **RAM vs disco** | a mesa que se limpa vs a gaveta que guarda |
