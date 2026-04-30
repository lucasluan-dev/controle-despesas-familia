import sqlite3
from datetime import date

import pandas as pd
import streamlit as st

DB_FILE = "despesas.db"


def get_conn():
    return sqlite3.connect(DB_FILE, check_same_thread=False)


def init_db(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS despesas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pessoa TEXT NOT NULL,
            descricao TEXT NOT NULL,
            valor REAL NOT NULL,
            data_vencimento TEXT NOT NULL,
            status_pagamento TEXT NOT NULL DEFAULT 'PENDENTE',
            info_adicional TEXT,
            criado_em TEXT NOT NULL
        )
        """
    )
    cols = conn.execute("PRAGMA table_info(despesas)").fetchall()
    col_names = [c[1] for c in cols]
    if "status_pagamento" not in col_names:
        conn.execute(
            "ALTER TABLE despesas ADD COLUMN status_pagamento TEXT NOT NULL DEFAULT 'PENDENTE'"
        )
    conn.commit()


def add_despesa(conn, pessoa, descricao, valor, data_vencimento, status_pagamento, info_adicional):
    conn.execute(
        """
        INSERT INTO despesas (pessoa, descricao, valor, data_vencimento, status_pagamento, info_adicional, criado_em)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            pessoa,
            descricao,
            valor,
            data_vencimento,
            status_pagamento,
            info_adicional,
            date.today().isoformat(),
        ),
    )
    conn.commit()


def list_despesas(conn, pessoa):
    query = """
        SELECT id, pessoa, descricao, valor, data_vencimento, status_pagamento, info_adicional, criado_em
        FROM despesas
    """
    params = ()
    if pessoa != "Todos":
        query += " WHERE pessoa = ?"
        params = (pessoa,)
    query += " ORDER BY data_vencimento ASC, id DESC"
    return pd.read_sql_query(query, conn, params=params)


def build_aviso_vencimento(data_vencimento, status_pagamento):
    if status_pagamento == "PAGO":
        return ""
    hoje = date.today()
    venc = date.fromisoformat(data_vencimento)
    dias = (venc - hoje).days
    if dias < 0:
        return f"Atrasado ha {abs(dias)} dia(s)"
    if dias == 0:
        return "Vence hoje"
    if dias == 1:
        return "Vence amanha"
    if 2 <= dias <= 3:
        return f"Vence em {dias} dias"
    return ""


def linha_por_status(row):
    status = row["status_pagamento"]
    hoje = date.today()
    venc = date.fromisoformat(row["data_vencimento"])
    dias = (venc - hoje).days

    if status == "PAGO":
        cor = "rgba(60, 198, 138, 0.25)"
    elif status == "ATRASADO" or dias < 0:
        cor = "rgba(244, 67, 54, 0.25)"
    elif 0 <= dias <= 3:
        cor = "rgba(255, 193, 7, 0.25)"
    else:
        cor = ""

    return [f"background-color: {cor}" if cor else "" for _ in row]


def apply_theme():
    st.markdown(
        """
        <style>
            :root {
                --bg: #061529;
                --text: #eaf2ff;
                --muted: #9db7dd;
                --accent: #2f7df6;
                --accent-2: #69a7ff;
                --border: #1d3f68;
            }
            .stApp {
                background:
                    radial-gradient(circle at 10% 10%, #133560 0%, rgba(19,53,96,0) 35%),
                    radial-gradient(circle at 90% 20%, #1b4b85 0%, rgba(27,75,133,0) 30%),
                    linear-gradient(170deg, #041022 0%, var(--bg) 55%, #020a16 100%);
                color: var(--text);
            }
            .main-card {
                background: linear-gradient(160deg, rgba(17,44,78,0.95), rgba(11,30,56,0.93));
                border: 1px solid var(--border);
                border-radius: 18px;
                padding: 1.2rem;
                box-shadow: 0 10px 30px rgba(0,0,0,0.25);
                margin-bottom: 1rem;
            }
            .title-text {
                font-size: 2rem;
                font-weight: 700;
                color: var(--text);
                margin: 0;
            }
            .subtitle-text {
                color: var(--muted);
                margin-top: 0.2rem;
                margin-bottom: 0;
            }
            div[data-testid="stMetric"], div[data-testid="stDataFrame"] {
                border: 1px solid var(--border);
                border-radius: 14px;
                overflow: hidden;
            }
            .stButton > button, .stForm button {
                background: linear-gradient(120deg, var(--accent), var(--accent-2)) !important;
                color: white !important;
                border: none !important;
                border-radius: 10px !important;
                font-weight: 600 !important;
            }
            section[data-testid="stSidebar"] {
                background: linear-gradient(180deg, #081a33 0%, #061326 100%);
                border-right: 1px solid var(--border);
            }
            label,
            .stMarkdown,
            .stTextInput label,
            .stNumberInput label,
            .stDateInput label,
            .stSelectbox label,
            .stMultiSelect label,
            .stRadio label,
            .stCheckbox label,
            .stSubheader {
                color: #ffffff !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main():
    st.set_page_config(page_title="Controle de Despesas da Familia", page_icon="💰", layout="wide")
    apply_theme()

    st.markdown(
        """
        <div class="main-card">
            <p class="title-text">Controle de Despesas da Familia</p>
            <p class="subtitle-text">Adicione despesas como em um site: nome, valor e data de vencimento.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    conn = get_conn()
    init_db(conn)

    st.sidebar.header("Filtro")
    pessoas_df = pd.read_sql_query(
        "SELECT DISTINCT pessoa FROM despesas WHERE pessoa IS NOT NULL AND TRIM(pessoa) <> '' ORDER BY pessoa ASC",
        conn,
    )
    pessoas = pessoas_df["pessoa"].tolist()
    pessoa_filtro = st.sidebar.selectbox("Ver despesas de:", ["Todos", *pessoas] if pessoas else ["Todos"])

    st.subheader("Adicionar despesa")
    with st.form("form_despesa", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            pessoa = st.text_input("Pessoa")
            descricao = st.text_input("Nome da despesa")
            valor = st.number_input("Valor (R$)", min_value=0.0, step=1.0, format="%.2f")
        with col2:
            data_vencimento = st.date_input("Data de vencimento", value=date.today())
            status_pagamento = st.selectbox("Status", ["PENDENTE", "PAGO", "ATRASADO"], index=0)
            info_adicional = st.text_input("Informacoes adicionais")

        submitted = st.form_submit_button("Salvar despesa")
        if submitted:
            if not pessoa.strip():
                st.error("Informe o nome da pessoa.")
            elif not descricao.strip():
                st.error("Informe o nome da despesa.")
            elif float(valor) <= 0:
                st.error("Informe um valor maior que zero.")
            else:
                add_despesa(
                    conn,
                    pessoa.strip(),
                    descricao.strip(),
                    float(valor),
                    data_vencimento.isoformat(),
                    status_pagamento,
                    info_adicional.strip(),
                )
                st.success("Despesa salva com sucesso.")

    st.subheader("Despesas cadastradas")
    df = list_despesas(conn, pessoa_filtro)
    if df.empty:
        st.info("Nenhuma despesa cadastrada ainda.")
    else:
        df["aviso_vencimento"] = df.apply(
            lambda row: build_aviso_vencimento(row["data_vencimento"], row["status_pagamento"]), axis=1
        )
        total = float(df["valor"].sum())
        st.metric("Total listado", f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        df_exibicao = df[
            [
                "id",
                "pessoa",
                "descricao",
                "valor",
                "data_vencimento",
                "status_pagamento",
                "aviso_vencimento",
                "info_adicional",
                "criado_em",
            ]
        ]
        st.dataframe(df_exibicao.style.apply(linha_por_status, axis=1), use_container_width=True)

        st.subheader("Resumo por pessoa")
        resumo = df.groupby("pessoa", as_index=False)["valor"].sum().sort_values("valor", ascending=False)
        st.bar_chart(resumo.set_index("pessoa"))


if __name__ == "__main__":
    main()
