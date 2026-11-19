
import os
import smtplib
import ssl

from dotenv import load_dotenv

load_dotenv()

email = os.getenv("GMAIL_ADDRESS", "").strip()
senha = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "")

context = ssl.create_default_context()


def testar_465():
    print("\n===== TESTE PORTA 465 =====")

    try:
        with smtplib.SMTP_SSL(
            "smtp.gmail.com",
            465,
            timeout=60,
            context=context
        ) as server:

            server.set_debuglevel(1)

            print("Conexão estabelecida.")
            print("Testando EHLO...")

            server.ehlo()

            print("Testando autenticação...")
            server.login(email, senha)

            print("SUCESSO: autenticação concluída na porta 465.")

    except Exception as erro:
        print(f"ERRO 465: {type(erro).__name__}: {erro}")


def testar_587():
    print("\n===== TESTE PORTA 587 =====")

    try:
        with smtplib.SMTP(
            "smtp.gmail.com",
            587,
            timeout=60
        ) as server:

            server.set_debuglevel(1)

            print("Conexão estabelecida.")
            print("Testando EHLO...")

            server.ehlo()

            print("Iniciando STARTTLS...")
            server.starttls(context=context)

            print("Testando novo EHLO...")
            server.ehlo()

            print("Testando autenticação...")
            server.login(email, senha)

            print("SUCESSO: autenticação concluída na porta 587.")

    except Exception as erro:
        print(f"ERRO 587: {type(erro).__name__}: {erro}")


if __name__ == "__main__":
    if not email or not senha:
        print("Configure GMAIL_ADDRESS e GMAIL_APP_PASSWORD no .env.")
    else:
        testar_465()
        testar_587()
