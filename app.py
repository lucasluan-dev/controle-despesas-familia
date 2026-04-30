import hashlib
import sqlite3
import tempfile
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

DB_FILE = f"{tempfile.gettempdir()}/despesas.db"
ONLINE_WINDOW_MINUTES = 5
MESES_PT_BR = {
    1: "janeiro",
    2: "fevereiro",
    3: "marco",
    4: "abril",
    5: "maio",
    6: "junho",
    7: "julho",
    8: "agosto",
    9: "setembro",
    10: "outubro",
    11: "novembro",
    12: "dezembro",
}


def get_conn():
    return sqlite3.connect(DB_FILE, check_same_thread=False)


def hash_senha(senha):
    return hashlib.sha256(senha.encode("utf-8")).hexdigest()


def agora_iso():
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def init_db(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            senha_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'USUARIO',
            ultimo_acesso TEXT,
            criado_em TEXT NOT NULL
        )
        """
    )

    cols_usuarios = conn.execute("PRAGMA table_info(usuarios)").fetchall()
    col_names_usuarios = [c[1] for c in cols_usuarios]
    if "role" not in col_names_usuarios:
        conn.execute("ALTER TABLE usuarios ADD COLUMN role TEXT NOT NULL DEFAULT 'USUARIO'")
    if "ultimo_acesso" not in col_names_usuarios:
        conn.execute("ALTER TABLE usuarios ADD COLUMN ultimo_acesso TEXT")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS despesas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pessoa TEXT NOT NULL,
            descricao TEXT NOT NULL,
            valor REAL NOT NULL,
            data_vencimento TEXT NOT NULL,
            status_pagamento TEXT NOT NULL DEFAULT 'PENDENTE',
            criado_por TEXT,
            info_adicional TEXT,
            criado_em TEXT NOT NULL
        )
        """
    )

    cols = conn.execute("PRAGMA table_info(despesas)").fetchall()
    col_names = [c[1] for c in cols]
    if "status_pagamento" not in col_names:
        conn.execute("ALTER TABLE despesas ADD COLUMN status_pagamento TEXT NOT NULL DEFAULT 'PENDENTE'")
    if "criado_por" not in col_names:
        conn.execute("ALTER TABLE despesas ADD COLUMN criado_por TEXT")
    conn.commit()


def criar_usuario(conn, username, senha):
    username = username.strip().lower()
    total_usuarios = conn.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
    role = "ADMIN" if total_usuarios == 0 else "USUARIO"
    try:
        conn.execute(
            "INSERT INTO usuarios (username, senha_hash, role, ultimo_acesso, criado_em) VALUES (?, ?, ?, ?, ?)",
            (username, hash_senha(senha), role, None, date.today().isoformat()),
        )
        conn.commit()
        if role == "ADMIN":
            return True, "Usuario criado com sucesso como ADMIN."
        return True, "Usuario criado com sucesso como USUARIO."
    except sqlite3.IntegrityError:
        return False, "Esse usuario ja existe."


def atualizar_ultimo_acesso(conn, username):
    conn.execute("UPDATE usuarios SET ultimo_acesso = ? WHERE username = ?", (agora_iso(), username))
    conn.commit()


def autenticar_usuario(conn, username, senha):
    username = username.strip().lower()
    row = conn.execute(
        "SELECT id, username, role FROM usuarios WHERE username = ? AND senha_hash = ?",
        (username, hash_senha(senha)),
    ).fetchone()
    if row:
        atualizar_ultimo_acesso(conn, row[1])
    return row


def listar_usuarios(conn):
    return pd.read_sql_query(
        "SELECT username, role, ultimo_acesso, criado_em FROM usuarios ORDER BY username ASC",
        conn,
    )


def formatar_data_pt_br(data_iso):
    dt = date.fromisoformat(data_iso)
    return f"{dt.day:02d} de {MESES_PT_BR[dt.month]} de {dt.year}"


def formatar_data_hora_pt_br(data_hora_iso):
    if not data_hora_iso:
        return "Nunca"
    dt = datetime.fromisoformat(data_hora_iso)
    return f"{dt.day:02d}/{dt.month:02d}/{dt.year} {dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}"


def formatar_moeda_br(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def usuario_esta_online(ultimo_acesso_iso):
    if not ultimo_acesso_iso:
        return False
    ultimo = datetime.fromisoformat(ultimo_acesso_iso)
    return datetime.now() - ultimo <= timedelta(minutes=ONLINE_WINDOW_MINUTES)


def calcular_status_real(data_vencimento_iso, status_informado):
    if status_informado == "PAGO":
        return "PAGO"
    hoje = date.today()
    venc = date.fromisoformat(data_vencimento_iso)
    if venc < hoje:
        return "ATRASADO"
    return "PENDENTE"


def add_despesa(conn, pessoa, descricao, valor, data_vencimento, status_pagamento, info_adicional, criado_por):
    status_real = calcular_status_real(data_vencimento, status_pagamento)
    conn.execute(
        """
        INSERT INTO despesas (pessoa, descricao, valor, data_vencimento, status_pagamento, criado_por, info_adicional, criado_em)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            pessoa,
            descricao,
            valor,
            data_vencimento,
            status_real,
            criado_por,
            info_adicional,
            date.today().isoformat(),
        ),
    )
    conn.commit()


def delete_despesa(conn, despesa_id):
    conn.execute("DELETE FROM despesas WHERE id = ?", (int(despesa_id),))
    conn.commit()


def list_despesas(conn, pessoa, username, role):
    query = """
        SELECT id, pessoa, descricao, valor, data_vencimento, status_pagamento, criado_por, info_adicional, criado_em
        FROM despesas
    """
    filtros = []
    params = []
    if role != "ADMIN":
        filtros.append("criado_por = ?")
        params.append(username)
    if pessoa != "Todos":
        filtros.append("pessoa = ?")
        params.append(pessoa)
    if filtros:
        query += " WHERE " + " AND ".join(filtros)
    query += " ORDER BY data_vencimento ASC, id DESC"
    return pd.read_sql_query(query, conn, params=tuple(params))


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
    status = row.get("status_real", row.get("Status_Real", "PENDENTE"))

    if status == "PAGO":
        cor = "rgba(60, 198, 138, 0.25)"
    elif status == "ATRASADO":
        cor = "rgba(244, 67, 54, 0.25)"
    else:
        hoje = date.today()
        venc_str = row.get(
            "data_vencimento",
            row.get("Data de vencimento", row.get("Data_Vencimento")),
        )
        venc = date.fromisoformat(venc_str)
        dias = (venc - hoje).days
        cor = "rgba(255, 193, 7, 0.25)" if 0 <= dias <= 3 else ""

    return [f"background-color: {cor}" if cor else "" for _ in row]


def apply_theme():
    st.markdown(
        """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@500;600;700&display=swap');
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
            .session-box {
                font-family: 'Poppins', sans-serif;
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid var(--border);
                border-radius: 12px;
                padding: 0.65rem 0.75rem;
                margin-bottom: 0.6rem;
            }
            .session-title {
                color: #cfe1ff;
                font-size: 0.75rem;
                letter-spacing: 0.06em;
                text-transform: uppercase;
                margin: 0 0 0.2rem 0;
            }
            .session-value {
                color: #ffffff;
                font-size: 1rem;
                font-weight: 600;
                margin: 0;
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
            div[data-testid="stMetricValue"] {
                color: #ffffff !important;
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


def check_auth(conn):
    if st.session_state.get("authenticated"):
        return True

    st.markdown("### Acesso da Familia")
    aba_login, aba_cadastro = st.tabs(["Entrar", "Criar usuario"])

    with aba_login:
        usuario_login = st.text_input("Usuario", key="login_usuario")
        senha_login = st.text_input("Senha", type="password", key="login_senha")
        if st.button("Entrar", key="btn_entrar"):
            user = autenticar_usuario(conn, usuario_login, senha_login)
            if user:
                st.session_state["authenticated"] = True
                st.session_state["username"] = user[1]
                st.session_state["role"] = user[2]
                st.rerun()
            st.error("Usuario ou senha invalidos.")

    with aba_cadastro:
        novo_usuario = st.text_input("Novo usuario", key="cad_usuario")
        nova_senha = st.text_input("Nova senha", type="password", key="cad_senha")
        confirmar_senha = st.text_input("Confirmar senha", type="password", key="cad_confirmar")
        if st.button("Criar conta", key="btn_criar"):
            if len(novo_usuario.strip()) < 3:
                st.error("Usuario deve ter pelo menos 3 caracteres.")
            elif len(nova_senha) < 6:
                st.error("Senha deve ter pelo menos 6 caracteres.")
            elif nova_senha != confirmar_senha:
                st.error("As senhas nao conferem.")
            else:
                ok, msg = criar_usuario(conn, novo_usuario, nova_senha)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)

    return False


def main():
    st.set_page_config(page_title="Controle de Despesas da Familia", page_icon="??", layout="wide")
    apply_theme()

    conn = get_conn()
    init_db(conn)

    if not check_auth(conn):
        st.stop()

    username = st.session_state.get("username", "")
    role = st.session_state.get("role", "USUARIO")
    atualizar_ultimo_acesso(conn, username)

    st.sidebar.markdown("### Sessao")
    st.sidebar.markdown(
        f"""
        <div class="session-box">
            <p class="session-title">Usuario</p>
            <p class="session-value">{username}</p>
        </div>
        <div class="session-box">
            <p class="session-title">Perfil</p>
            <p class="session-value">{role}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    usuarios_df = listar_usuarios(conn)
    st.sidebar.markdown("### Usuarios cadastrados")
    for nome in usuarios_df["username"].tolist():
        st.sidebar.write(f"- {nome}")

    if role == "ADMIN":
        st.sidebar.markdown("### Status de acesso")
        status_df = usuarios_df.copy()
        status_df["online"] = status_df["ultimo_acesso"].apply(lambda x: "Online" if usuario_esta_online(x) else "Offline")
        status_df["ultimo_acesso_fmt"] = status_df["ultimo_acesso"].apply(formatar_data_hora_pt_br)
        st.sidebar.dataframe(
            status_df[["username", "role", "online", "ultimo_acesso_fmt"]],
            use_container_width=True,
            hide_index=True,
        )

    if st.sidebar.button("Sair"):
        atualizar_ultimo_acesso(conn, username)
        st.session_state["authenticated"] = False
        st.session_state["username"] = ""
        st.session_state["role"] = ""
        st.rerun()

    st.markdown(
        """
        <div class="main-card">
            <p class="title-text">Controle de Despesas da Familia</p>
            <p class="subtitle-text">Adicione despesas como em um site: nome, valor e data de vencimento.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.sidebar.header("Filtro")
    pessoas_df = pd.read_sql_query(
        "SELECT DISTINCT pessoa FROM despesas WHERE pessoa IS NOT NULL AND TRIM(pessoa) <> '' ORDER BY pessoa ASC",
        conn,
    )
    pessoas = pessoas_df["pessoa"].tolist()
    if role == "ADMIN":
        busca_usuario = st.sidebar.text_input("Pesquisar usuario", value="", placeholder="Digite o nome...")
        termo = busca_usuario.strip().lower()
        pessoas_filtradas = [p for p in pessoas if termo in p.lower()] if termo else pessoas
        opcoes_filtro = ["Todos", *pessoas_filtradas] if pessoas_filtradas else ["Todos"]
    else:
        opcoes_filtro = [username]
    pessoa_filtro = st.sidebar.selectbox("Ver despesas de:", opcoes_filtro)

    st.subheader("Adicionar despesa")
    with st.form("form_despesa", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            pessoa = st.text_input("Pessoa")
            descricao = st.text_input("Nome da despesa")
            valor = st.number_input("Valor (R$)", min_value=0.0, step=1.0, format="%.2f")
        with col2:
            data_vencimento = st.date_input("Data de vencimento", value=date.today(), format="DD/MM/YYYY")
            status_pagamento = st.selectbox("Status", ["PENDENTE", "PAGO"], index=0)
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
                    username,
                )
                st.success("Despesa salva com sucesso.")

    st.subheader("Despesas cadastradas")
    df = list_despesas(conn, pessoa_filtro, username, role)
    if df.empty:
        st.info("Nenhuma despesa cadastrada ainda.")
    else:
        df["status_real"] = df.apply(
            lambda row: calcular_status_real(row["data_vencimento"], row["status_pagamento"]), axis=1
        )
        df["aviso_vencimento"] = df.apply(
            lambda row: build_aviso_vencimento(row["data_vencimento"], row["status_real"]), axis=1
        )
        df["data_vencimento_pt"] = df["data_vencimento"].apply(formatar_data_pt_br)
        df["criado_em_pt"] = df["criado_em"].apply(formatar_data_pt_br)

        total = float(df["valor"].sum())
        st.metric("Total Listado", formatar_moeda_br(total))

        df_exibicao = df[
            [
                "id",
                "pessoa",
                "descricao",
                "valor",
                "data_vencimento",
                "data_vencimento_pt",
                "status_real",
                "aviso_vencimento",
                "info_adicional",
                "criado_em_pt",
            ]
        ]
        df_exibicao["valor"] = df_exibicao["valor"].apply(formatar_moeda_br)
        df_exibicao = df_exibicao.rename(
            columns={
                "id": "Id",
                "pessoa": "Pessoa",
                "descricao": "Descricao",
                "valor": "Valor",
                "data_vencimento": "Data de vencimento",
                "data_vencimento_pt": "Data de vencimento (pt)",
                "status_real": "Status real",
                "aviso_vencimento": "Aviso de vencimento",
                "info_adicional": "Info adicional",
                "criado_em_pt": "Criado em (pt)",
            }
        )

        st.dataframe(df_exibicao.style.apply(linha_por_status, axis=1), use_container_width=True, hide_index=True)

        st.subheader("Acoes")
        st.caption("Clique na lixeira para excluir uma despesa.")
        for _, row in df.iterrows():
            c1, c2, c3, c4 = st.columns([2.3, 3.3, 2, 0.7])
            c1.write(f"{row['pessoa']} - R$ {row['valor']:.2f}".replace(".", ","))
            c2.write(f"{row['descricao']} ({formatar_data_pt_br(row['data_vencimento'])})")
            c3.write(row["status_real"])
            if c4.button("???", key=f"del_{int(row['id'])}", help="Excluir despesa"):
                delete_despesa(conn, int(row["id"]))
                st.success("Despesa excluida com sucesso.")
                st.rerun()

        if role == "ADMIN":
            st.subheader("Resumo por Usuario")
            df_resumo = list_despesas(conn, "Todos", username, role)
            df_resumo["status_real"] = df_resumo.apply(
                lambda row: calcular_status_real(row["data_vencimento"], row["status_pagamento"]), axis=1
            )
            resumo_admin = (
                df_resumo.assign(
                    valor_pago=df_resumo.apply(lambda r: r["valor"] if r["status_real"] == "PAGO" else 0.0, axis=1),
                    valor_pendente=df_resumo.apply(lambda r: r["valor"] if r["status_real"] == "PENDENTE" else 0.0, axis=1),
                    valor_atrasado=df_resumo.apply(lambda r: r["valor"] if r["status_real"] == "ATRASADO" else 0.0, axis=1),
                )
                .groupby("pessoa", as_index=False)[["valor_pago", "valor_pendente", "valor_atrasado", "valor"]]
                .sum()
                .sort_values("pessoa")
                .rename(
                    columns={
                        "pessoa": "usuario",
                        "valor_pago": "pago",
                        "valor_pendente": "pendente",
                        "valor_atrasado": "atrasado",
                        "valor": "total",
                    }
                )
            )
            for col in ["pago", "pendente", "atrasado", "total"]:
                resumo_admin[col] = resumo_admin[col].apply(formatar_moeda_br)
            resumo_admin = resumo_admin.rename(
                columns={
                    "usuario": "Usuario",
                    "pago": "Pago",
                    "pendente": "Pendente",
                    "atrasado": "Atrasado",
                    "total": "Total",
                }
            )
            st.dataframe(resumo_admin, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
