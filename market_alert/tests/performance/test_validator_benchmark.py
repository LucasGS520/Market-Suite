from app.utils.data_quality_validator import DataQualityValidator

def test_data_quality_validator_performance(benchmark):
    validator = DataQualityValidator()
    data = {
        "name": "Produto Teste",
        "url": "https://example.com/prod",
        "current_price": "R$ 9,99",
        "thumbnail": "https://example.com/img.jpg",
        "seller": "Loja",
        "shipping": "Frete Grátis"
    }
    benchmark(validator.validate, data)
