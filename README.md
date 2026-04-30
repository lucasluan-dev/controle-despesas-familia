# Sistema de Gerenciamento de Despesas

Este projeto agora tem duas formas de uso:

- `despesas.py`: versao em terminal (menu de texto)
- `app.py`: versao web com interface (Streamlit)

## Funcionalidades da interface web

- Cadastro de despesas por pessoa (`Lucas`, `Pai`, `Mae`)
- Listagem com filtro por pessoa
- Total das despesas listadas
- Grafico de resumo por pessoa
- Armazenamento em banco local SQLite (`despesas.db`)

## Rodar localmente (interface web)

1. Entre na pasta do projeto:

```powershell
cd d:\Python\despesas
```

2. Instale as dependencias:

```powershell
pip install -r requirements.txt
```

3. Execute o app:

```powershell
streamlit run app.py
```

4. Abra o link local que aparece no terminal (normalmente `http://localhost:8501`).

## Publicar e compartilhar link (Streamlit Community Cloud)

1. Crie uma conta em `https://share.streamlit.io/`.
2. Suba esta pasta para um repositorio no GitHub.
3. No Streamlit Cloud, clique em **New app**.
4. Selecione o repositorio e defina:
- Main file path: `despesas/app.py` (ou `app.py` se a pasta `despesas` for a raiz do repo)
5. Clique em **Deploy**.
6. O Streamlit gera um link publico para compartilhar com seus pais.

## Observacoes

- A versao web usa `despesas.db` e nao depende do `despesas.csv`.
- Se quiser, depois podemos adicionar login simples por senha para cada pessoa.
