""" Inicialização dos modelos para importação do SQLAlchemy """

#Importa os modelos aqui para o SQLAlchemy reconhecer na criação de tabelas
from .models_users import User
from .models_products import MonitoredProduct, CompetitorProduct
from .models_scraping_errors import ScrapingError
from .models_comparisons import PriceComparison
from .models_alerts import AlertRule, NotificationLog
