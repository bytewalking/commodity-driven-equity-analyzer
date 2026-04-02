from datetime import datetime, timedelta

COMMODITY_CONFIG = {
    "铝 (Aluminum)": {
        "futures_symbol": "AL0",
        "color": "#4472C4",
        "unit": "元/吨",
        "related_stocks": [
            {"code": "601600", "name": "中国铝业", "industry": "有色金属-铝"},
            {"code": "600219", "name": "南山铝业", "industry": "有色金属-铝"},
            {"code": "000807", "name": "云铝股份", "industry": "有色金属-铝"},
            {"code": "000933", "name": "神火股份", "industry": "有色金属-铝"},
            {"code": "002532", "name": "天山铝业", "industry": "有色金属-铝"},
            {"code": "601677", "name": "明泰铝业", "industry": "有色金属-铝"},
        ],
    },
    "黄金 (Gold)": {
        "futures_symbol": "AU0",
        "color": "#FFD700",
        "unit": "元/克",
        "related_stocks": [
            {"code": "601899", "name": "紫金矿业", "industry": "有色金属-黄金"},
            {"code": "600547", "name": "山东黄金", "industry": "有色金属-黄金"},
            {"code": "600489", "name": "中金黄金", "industry": "有色金属-黄金"},
            {"code": "002155", "name": "湖南黄金", "industry": "有色金属-黄金"},
            {"code": "601069", "name": "西藏黄金", "industry": "有色金属-黄金"},
            {"code": "600988", "name": "赤峰黄金", "industry": "有色金属-黄金"},
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

DEFAULT_START = (datetime.now() - timedelta(days=3650)).strftime("%Y%m%d")  # 10年历史
DEFAULT_END = datetime.now().strftime("%Y%m%d")
