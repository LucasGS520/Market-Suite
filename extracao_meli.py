import smtplib
import cloudscraper
from bs4 import BeautifulSoup
import time
from datetime import datetime

# Configurações do e-mail
EMAIL_REMETENTE = ""
SENHA_EMAIL = ""  # Senha de aplicativo
EMAIL_DESTINO = [
]

# Lista de produtos para monitoramento
produtos = [
    {
        "nome": "Farol Uno Mille Fire",
        "meu_url": "https://produto.mercadolivre.com.br/MLB-1053147838-par-farol-uno-mille-fire-economy-way-04-2005-2006-2007-2008-_JM",
        "concorrente_url": "https://produto.mercadolivre.com.br/MLB-1984362204-grade-dianteira-mitsubishi-triton-l200-gl-2012-2013-a-2017-_JM"
    },
    {
        "nome": "Tes01",
        "meu_url": "https://produto.mercadolivre.com.br/MLB-1053147838-par-farol-uno-mille-fire-economy-way-04-2005-2006-2007-2008-_JM",
        "concorrente_url": "https://produto.mercadolivre.com.br/MLB-1984362204-grade-dianteira-mitsubishi-triton-l200-gl-2012-2013-a-2017-_JM"
    },
    {
        "nome": "FAROL HILUX 2005 A 2011 SEM JUROS",
        "meu_url": "https://produto.mercadolivre.com.br/MLB-1087764038-farol-hilux-srv-2009-2010-2011-serve-2005-2006-2007-2008-_JM",
        "concorrente_url": "https://produto.mercadolivre.com.br/MLB-3650248091-farol-hilux-srv-2009-2010-2011-serve-2005-2006-2007-2008-le-_JM"
    },
    {
        "nome": "PAR FAROL HILUX 2005 A 2011 COM JUROS",
        "meu_url": "https://produto.mercadolivre.com.br/MLB-1307674533-par-farol-hilux-srv-2009-2010-2011-srv-foco-simples-cromado-_JM",
        "concorrente_url": "https://produto.mercadolivre.com.br/MLB-2646760896-par-farol-hilux-srv-2009-2010-2011-cromado-pickup-_JM"
    },
    {
        "nome": "PAR FAROL HILUX 2005 A 2011 SEM JUROS",
        "meu_url": "https://produto.mercadolivre.com.br/MLB-2019938176-par-farol-hilux-srv-2009-2010-2011-srv-foco-simples-cristal-_JM",
        "concorrente_url": "https://produto.mercadolivre.com.br/MLB-2646760896-par-farol-hilux-srv-2009-2010-2011-cromado-pickup-_JM"
    },
    {
        "nome": "PAR LANTERNA HILUX SEM JUROS",
        "meu_url": "https://produto.mercadolivre.com.br/MLB-3892474116-kit-par-lanterna-led-hilux-2016-a-2024-modelo-2021-srx-_JM",
        "concorrente_url": "https://produto.mercadolivre.com.br/MLB-5034414606-par-lanterna-hilux-srx-2019-2020-2021-2022-2023-2024-com-led-_JM"
    },
    {
        "nome": "PAR LANTERNA HILUX COM JUROS",
        "meu_url": "https://produto.mercadolivre.com.br/MLB-3892485262-kit-lanterna-traseira-led-hilux-16-17-18-19-20-21-22-23-24-_JM",
        "concorrente_url": "https://produto.mercadolivre.com.br/MLB-3529391643-par-farol-traseiro-hilux-srv-srx-16-17-18-19-20-21-2022-2023-_JM"
    },
    {
        "nome": "GRADE RADIADOR TRITON L200",
        "meu_url": "https://produto.mercadolivre.com.br/MLB-1984362204-grade-dianteira-mitsubishi-triton-l200-gl-2012-2013-a-2017-_JM",
        "concorrente_url": "https://produto.mercadolivre.com.br/MLB-3735121175-grade-dianteira-l200-triton-2012-2013-2014-2015-gls-glx-hls-_JM"
    }
]

precos_anteriores = {}

def obter_preco(url):
    scraper = cloudscraper.create_scraper()
    try:
        response = scraper.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        preco_element = soup.find("span", {"class": "andes-money-amount__fraction"})

        if preco_element:
            preco_str = preco_element.text.strip().replace(".", "").replace(",", ".")
            preco = float(preco_str)
            print(f"✅ Preço encontrado em {url}: R$ {preco:.2f}")
            return preco
        else:
            print(f"⚠️ Preço não encontrado na página: {url}")
    except Exception as e:
        print(f"❌ Erro ao acessar {url}: {e}")
    return None

def enviar_email(produto, preco_meu, preco_concorrente, meu_url, concorrente_url, data_monitoramento):
    status = "⚠️ ATENÇÃO! O CONCORRENTE TEM O MELHOR PREÇO!"
    mensagem = (
        f"🔎 Monitoramento de preços - {produto}\n\n"
        f"📅 Data: {data_monitoramento}\n\n"
        f"📌 Seu preço: R$ {preco_meu:.2f} -> {meu_url}\n"
        f"📌 Preço do concorrente: R$ {preco_concorrente:.2f} -> {concorrente_url}\n\n"
        "⚠️ Considere ajustar seu preço para se manter competitivo!"
    )

    msg = f"Subject: ALERTA DE PREÇO - {produto} - {status}\n\n{mensagem}"

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(EMAIL_REMETENTE, SENHA_EMAIL)
        server.sendmail(EMAIL_REMETENTE, EMAIL_DESTINO, msg.encode("utf-8"))
        server.quit()
        print(f"✅ E-mail enviado sobre {produto} ({data_monitoramento})")
    except Exception as e:
        print(f"❌ Erro ao enviar e-mail: {e}")

# Loop de monitoramento
while True:
    data_monitoramento = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    print(f"\n🔄 Iniciando monitoramento de preços... ({data_monitoramento})")

    for produto in produtos:
        preco_meu = obter_preco(produto["meu_url"])
        preco_concorrente = obter_preco(produto["concorrente_url"])

        if preco_meu is None or preco_concorrente is None:
            print(f"⚠️ Não foi possível obter todos os preços para {produto['nome']}. Pulando...")
            continue

        print(f"📊 {produto['nome']}: Meu preço R$ {preco_meu:.2f} | Concorrente R$ {preco_concorrente:.2f}")

        if preco_concorrente < preco_meu:
            print(f"🚨 ALERTA: Seu preço está mais alto que o do concorrente!")
            enviar_email(produto["nome"], preco_meu, preco_concorrente, produto["meu_url"], produto["concorrente_url"], data_monitoramento)
        else:
            print(f"✅ Preço OK: Seu preço está competitivo.")

    print(f"⏳ Monitoramento finalizado às {data_monitoramento}. Aguardando 30 minutos...\n")
    time.sleep(1800)



