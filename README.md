# Jornada Musical com IA e Spotify

Protótipo que transforma uma situação descrita pelo usuário em uma fila local com
progressão de DJ: chegada, aquecimento, pico e fechamento. Em vez de gerar só
uma lista de músicas parecidas, o app monta uma narrativa musical e toca faixa
por faixa com o player embutido do Spotify.

## O que o sistema faz

- Conecta ao Spotify por OAuth PKCE no navegador.
- Gera uma seleção musical do zero com Gemini 3.1 Flash Lite.
- Busca automaticamente as faixas sugeridas no Spotify.
- Recebe um briefing simples em formato de conversa: situação, lugar, energia
  inicial, energia final, grau de descoberta e duração aproximada.
- Organiza as músicas em quatro blocos:
  - Chegada
  - Aquecimento
  - Pico
  - Fechamento
- Explica o caminho da curadoria sem mostrar uma lista gigante de músicas.
- Permite reorganizar a curadoria por feedback textual no chat.
- Mantém a fila gerada localmente no app.
- Permite escolher a música atual dentro da fila local.
- Mostra o player de música do Spotify embutido no próprio app.

O token do Spotify fica no navegador. O briefing e o feedback são enviados ao
Gemini para gerar a curadoria; as buscas de faixa são feitas diretamente na API
do Spotify pelo navegador. O app não cria playlist na conta do usuário.

## Configuração

Crie um app no [Spotify for Developers](https://developer.spotify.com/dashboard)
e cadastre exatamente a URL local como Redirect URI:

```text
http://127.0.0.1:8000/
```

Crie um arquivo `.env` na raiz do projeto:

```dotenv
SPOTIFY_CLIENT_ID="seu_client_id"
GEMINI_API_KEY="sua_chave_gemini"
GEMINI_MUSIC_MODEL="gemini-3.1-flash-lite"
```

Depois execute:

```bash
python3 -m pip install -r requirements.txt
npm --prefix frontend install
npm --prefix frontend run build
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Acesse:

```text
http://127.0.0.1:8000
```

## Como usar

1. Conecte o Spotify.
2. Descreva a situação, por exemplo:

```text
Vou fazer uma resenha em casa com amigos. Quero começar leve, subir a energia
aos poucos e chegar num pico dançante sem ficar pesado demais.
```

3. Clique em `Gerar playlist`.
4. O app monta a fila local e carrega a primeira música no player.
5. Use `Anterior`, `Próxima` ou clique numa música da fila para trocar a faixa.
6. Leia a explicação curta e mande feedbacks pelo chat se quiser ajustar.

## Frontend

O frontend agora é React + TypeScript com Vite. O código fonte fica em:

```text
frontend/
  src/App.tsx        experiência principal, Spotify OAuth e fila local
  src/styles.css     layout e componentes visuais
  vite.config.ts     build para app/static
```

O build gera os arquivos finais em `app/static`, que continuam sendo servidos
pelo FastAPI.

Durante desenvolvimento do frontend:

```bash
npm --prefix frontend run dev
```

Para atualizar a versão servida pelo FastAPI:

```bash
npm --prefix frontend run build
```

## Testes

Os testes usam apenas a biblioteca padrão do Python:

```bash
python3 -m unittest discover -s tests
```

## Deploy com Docker

```bash
docker build -t jornada-musical .
docker run -p 8000:8000 jornada-musical
```

Depois acesse:

```text
http://localhost:8000
```

## Estrutura

```text
app/
  main.py              API FastAPI e arquivos estáticos
  groq_music.py        cliente musical Gemini, mantido com nome legado
  groq_vision.py       cliente antigo de visão mantido por compatibilidade
  domain.py            motor de jornada e lógica legada de energia
  schemas.py           contratos da API
  static/              build compilado do frontend
frontend/
  src/                 frontend React + TypeScript
tests/
  test_domain.py       testes da lógica principal
  test_groq_vision.py  testes do contrato multimodal legado
  test_groq_music.py   testes da pesquisa e normalização musical
Dockerfile             imagem de produção
requirements.txt       dependências de runtime
```

## Privacidade e limites

O app não usa câmera no fluxo principal. A curadoria depende da qualidade da
resposta da IA e da disponibilidade das faixas no Spotify. Spotify comum é
destinado a uso pessoal; uso público ou comercial exige verificar licenciamento
e termos aplicáveis.
