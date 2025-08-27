from market_scraper.utils.data_quality_validator import DataQualityValidator

def test_data_quality_validator_performance(benchmark):
    validator = DataQualityValidator()
    data = {
        "name": "Produto Teste",
        "current_price": "R$ 9,99",
    }
    benchmark(validator.validate, data)
