# DJ Copilot com Groq Vision e Spotify

Protótipo end to end que observa a atividade coletiva da pista, consulta um modelo
multimodal da Groq a cada minuto e escolhe uma faixa de uma playlist Spotify
desordenada.

## O que o sistema faz

- Mede continuamente diferença entre frames como sinal auxiliar.
- Guarda até cinco amostras JPEG de baixa resolução no navegador.
- A cada minuto, envia somente essas amostras para o Groq Vision.
- Importa uma playlist Spotify sem depender da ordem das músicas.
- Pesquisa automaticamente todas as faixas com o Groq Compound e busca na web.
- Cria para cada música um perfil com energia, BPM, gênero, dançabilidade e
  confiança; os resultados ficam no `localStorage` do navegador.
- Faz o match localmente entre a leitura da câmera e os perfis musicais,
  ponderando energia, dançabilidade, continuidade de BPM e confiança.
- Mantém os sliders como correção manual quando a pesquisa errar.
- Controla um dispositivo Spotify existente por OAuth PKCE.
- Exige duas leituras coerentes e, por padrão, 120 segundos de reprodução antes
  de uma troca automática.
- Continua funcionando sem Groq, usando apenas a tendência de diferença entre
  frames.

O token do Spotify e as URIs de reprodução permanecem no navegador. Para montar
o perfil musical, título e artista das faixas são enviados ao backend e ao Groq
Compound para pesquisa web.

## Configuracao

Crie um app no [Spotify for Developers](https://developer.spotify.com/dashboard)
e cadastre exatamente a URL local como Redirect URI:

```text
http://127.0.0.1:8000/
```

Crie um arquivo `.env` na raiz do projeto:

```dotenv
SPOTIFY_CLIENT_ID="seu_client_id"
GROQ_API_KEY="sua_chave_groq"
GROQ_VISION_MODEL="meta-llama/llama-4-scout-17b-16e-instruct"
GROQ_MUSIC_MODEL="groq/compound-mini"
```

Depois execute:

```bash
python3 -m pip install -r requirements.txt
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Configurações opcionais:

```bash
export VISION_INTERVAL_SECONDS=60
export MIN_TRACK_SECONDS=120
```

O controle de reprodução requer uma conta Spotify Premium e um dispositivo
Spotify aberto. Depois de conectar, importe uma URL de playlist, aguarde a
pesquisa automática, revise os perfis se desejar e selecione o dispositivo.

Ao importar uma playlist pela primeira vez, a pesquisa pode levar algum tempo:
o navegador envia lotes de até dois títulos/artistas ao backend. Resultados já
pesquisados são reutilizados nas próximas importações.

Sem as integrações, basta executar o mesmo servidor e acessar:

```text
http://127.0.0.1:8000
```

## Testes

Os testes usam apenas a biblioteca padrao do Python:

```bash
python3 -m unittest discover -s tests
```

## Deploy com Docker

```bash
docker build -t dj-interativo .
docker run -p 8000:8000 dj-interativo
```

Depois acesse:

```text
http://localhost:8000
```

## Estrutura

```text
app/
  main.py              API FastAPI e arquivos estaticos
  groq_vision.py       cliente multimodal e validacao das respostas
  groq_music.py        pesquisa web e perfil musical via Groq Compound
  domain.py            analise de movimento e selecao musical
  schemas.py           contratos da API
  static/              frontend web
tests/
  test_domain.py       testes da logica principal
  test_groq_vision.py  testes do contrato multimodal
  test_groq_music.py   testes da pesquisa e normalizacao musical
Dockerfile             imagem de producao
requirements.txt       dependencias de runtime
```

## Privacidade e limites

O sistema não reconhece rostos nem tenta inferir emoções. As imagens de baixa
resolução são enviadas ao Groq somente durante a análise e não são persistidas
pelo aplicativo. A leitura representa atividade corporal aparente, não prova
que o público gostou da música.

Spotify comum é destinado a uso pessoal. Este protótipo serve para demonstração;
uso público ou comercial exige verificar licenciamento e os termos aplicáveis.
