from datetime import datetime, timedelta

COMMODITY_CONFIG = {
    "铝 (Aluminum)": {
        "futures_symbol": "AL0",
        "color": "#4472C4",
        "unit": "元/吨",
        "related_stocks": [
            {"code": "601600", "name": "中国铝业", "industry": "有色金属-铝"},
            {"code": "000807", "name": "云铝股份",  "industry": "有色金属-铝"},
            {"code": "600219", "name": "南山铝业", "industry": "有色金属-铝"},
            {"code": "601677", "name": "明泰铝业", "industry": "有色金属-铝"},
        ],
    },
    "煤炭 (Coal)": {
        "futures_symbol": "ZC0",
        "color": "#7030A0",
        "unit": "元/吨",
        "related_stocks": [
            {"code": "601088", "name": "中国神华", "industry": "能源-煤炭"},
            {"code": "600188", "name": "兖矿能源", "industry": "能源-煤炭"},
            {"code": "601225", "name": "陕西煤业", "industry": "能源-煤炭"},
            {"code": "601898", "name": "中煤能源", "industry": "能源-煤炭"},
            {"code": "000983", "name": "山西焦煤", "industry": "能源-煤炭"},
        ],
    },
    "铜 (Copper)": {
        "futures_symbol": "CU0",
        "color": "#FF7A00",
        "unit": "元/吨",
        "related_stocks": [
            {"code": "600362", "name": "江西铜业", "industry": "有色金属-铜"},
            {"code": "000630", "name": "铜陵有色", "industry": "有色金属-铜"},
            {"code": "601168", "name": "西部矿业", "industry": "有色金属-铜"},
        ],
    },
    "原油 (Crude Oil)": {
        "futures_symbol": "SC0",
        "color": "#C00000",
        "unit": "元/桶",
        "related_stocks": [
            {"code": "601857", "name": "中国石油", "industry": "能源-石油"},
            {"code": "600028", "name": "中国石化", "industry": "能源-石油"},
        ],
    },
}

DEFAULT_STRATEGY = {
    "buy_threshold": -2.0,
    "sell_threshold": 2.0,
    "stop_loss": -0.05,
    "zscore_window": 60,
    "use_trend_filter": False,
}

DEFAULT_START = (datetime.now() - timedelta(days=730)).strftime("%Y%m%d")
DEFAULT_END = datetime.now().strftime("%Y%m%d")
