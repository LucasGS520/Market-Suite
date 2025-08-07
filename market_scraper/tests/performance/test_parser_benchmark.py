from scraper_app.services.services_parser import parse_product_details

html_sample = """
<html>
  <head>
    <meta property="og:image" content="https://example.com/thumb.jpg" />
    <script type="application/ld+json">
    {
      "@context": "https://schema.org/",
      "@type": "Product",
      "name": "Tênis de Corrida",
      "offers": {
        "@type": "Offer",
        "price": "199.99",
        "availability": "https://schema.org/InStock"
      }
    }
    </script>
  </head>
  <body>
    <h1 class="ui-pdp-tittle">Tênis de Corrida</h1>
    <span class="ui-seller-data-header__title">Vendedor Oficial</span>
    <span class="andes-money-amount__fraction">199</span>
    <span class="andes-money-amount__cents">99</span>
    <p class="ui-pdp-color--GREEN">Frete grátis</p>
  </body>
</html>
"""

def test_parse_product_details_performance(benchmark):
    benchmark(parse_product_details, html_sample, url="https://produto.mercadolivre.com.br/ABC123")
