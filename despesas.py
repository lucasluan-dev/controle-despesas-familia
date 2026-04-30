import csv
import datetime
import os
import re
import smtplib
from email.mime.text import MIMEText

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.path.join(BASE_DIR, 'despesas.csv')
CSV_HEADERS = ['descricao', 'valor', 'data_vencimento', 'info_adicional', 'email_lembrete']


def garantir_arquivo_csv():
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(CSV_HEADERS)


def adicionar_despesa():
    garantir_arquivo_csv()
    descricao = input('Descricao da despesa: ')
    valor = input('Valor: ')
    data_vencimento = input('Data de vencimento (YYYY-MM-DD): ')
    info_adicional = input('Informacoes adicionais: ')
    email_lembrete = input('Email para lembrete: ')

    with open(CSV_FILE, 'a', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow([descricao, valor, data_vencimento, info_adicional, email_lembrete])
    print('Despesa adicionada com sucesso!')


def listar_despesas():
    try:
        garantir_arquivo_csv()
        with open(CSV_FILE, 'r', encoding='utf-8') as file:
            reader = csv.reader(file)
            print('Despesas:')
            for row in reader:
                print(row)
    except FileNotFoundError:
        print('Arquivo despesas.csv nao encontrado.')


def verificar_lembretes():
    today = datetime.date.today().isoformat()
    lembretes_enviados = []
    try:
        garantir_arquivo_csv()
        with open(CSV_FILE, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                if row['data_vencimento'] == today:
                    enviar_email(row['email_lembrete'], row['descricao'], row['valor'])
                    lembretes_enviados.append(row['descricao'])

        if lembretes_enviados:
            print(f"Lembretes enviados para: {', '.join(lembretes_enviados)}")
        else:
            print('Nenhum lembrete para hoje.')
    except FileNotFoundError:
        print('Arquivo despesas.csv nao encontrado.')


def enviar_email(to_email, descricao, valor):
    from_email = os.getenv('DESPESAS_EMAIL_FROM', '')
    password = os.getenv('DESPESAS_EMAIL_PASSWORD', '')
    smtp_server = 'smtp.gmail.com'
    smtp_port = 587

    if not from_email or not password:
        print('Configuracao de email ausente. Defina DESPESAS_EMAIL_FROM e DESPESAS_EMAIL_PASSWORD.')
        return

    local_part = to_email.split('@')[0].strip().lower()
    first_chunk = re.split(r'[._+\-]', local_part)[0]
    name_match = re.match(r'[a-z]+', first_chunk)
    extracted = name_match.group(0) if name_match else ''

    common_names = [
        'ana', 'bruno', 'carlos', 'daniel', 'eduardo', 'felipe', 'gabriel',
        'giovana', 'gustavo', 'isabela', 'joao', 'jose', 'juliana', 'larissa',
        'leticia', 'lucas', 'luiza', 'marcos', 'maria', 'mateus', 'paulo',
        'pedro', 'rafael', 'renata', 'rodrigo', 'samuel', 'sarah', 'thiago',
        'vinicius', 'vitoria'
    ]
    matched_common_name = next(
        (n for n in sorted(common_names, key=len, reverse=True) if extracted.startswith(n)),
        ''
    )
    name = matched_common_name.capitalize() if matched_common_name else (extracted.capitalize() if extracted else 'Amigo(a)')

    subject = 'Lembrete de Pagamento de Despesa'
    body = (
        f'Ola, {name},\n\n'
        f'Este e um lembrete para pagar a despesa: {descricao}\n'
        f'Valor: {valor}\n\n'
        'Por favor, efetue o pagamento hoje.\n\n'
        'Atenciosamente,\nSistema de Despesas'
    )

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = from_email
    msg['To'] = to_email

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(from_email, password)
        server.sendmail(from_email, to_email, msg.as_string())
        server.quit()
        print(f'Email enviado para {to_email}')
    except Exception as e:
        print(f'Erro ao enviar email: {e}')


def main():
    while True:
        print('\nSistema de Gerenciamento de Despesas')
        print('1. Adicionar despesa')
        print('2. Listar despesas')
        print('3. Verificar lembretes (enviar emails se vencem hoje)')
        print('4. Sair')
        try:
            escolha = input('Escolha uma opcao: ')
        except EOFError:
            print('\nEntrada encerrada. Saindo do programa.')
            break

        if escolha == '1':
            adicionar_despesa()
        elif escolha == '2':
            listar_despesas()
        elif escolha == '3':
            verificar_lembretes()
        elif escolha == '4':
            break
        else:
            print('Opcao invalida.')


if __name__ == '__main__':
    main()
