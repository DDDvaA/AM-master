import json
import statistics
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import app


CATEGORY = "Pet Supplies > Cats > Litter Boxes"
OUTPUT = Path(r"C:\Users\DELL-PC\Documents\New project\outputs\智能猫砂盆七国产品开发分析\litter_analysis_data.json")
COUNTRY_ORDER = list(app.COUNTRIES)

FEATURES = {
    "开放式/大入口": ["open top", "open-top", "offen", "ouvert", "aperto", "abierto", "diseño abierto"],
    "APP/WiFi": ["app", "wifi", "wi-fi", "wlan", "application"],
    "安全/防夹": ["anti-pinch", "safety sensor", "safety sensors", "sicherheit", "sicher", "sécurité", "antipellizco", "anti-pellizco", "sicurezza"],
    "除臭": ["odor", "odour", "smell", "geruch", "odeur", "odore", "olor", "desodoriz"],
    "多猫": ["multi-cat", "multiple cats", "mehrkatzen", "plusieurs chats", "più gatti", "varios gatos", "múltiples gatos"],
    "体重/健康": ["weight", "health", "gewicht", "poids", "peso", "salud"],
    "摄像头/AI": ["camera", "ai ", "kamera", "caméra", "fotocamera", "cámara"],
    "自动打包": ["self-packing", "auto-packing", "automatic packing", "autoempacable"],
    "大容量/XXL": ["xxl", "large capacity", "large-capacity", "großraum", "grande capacité", "gran capacidad", "grande capacità", "90l", "106l"],
    "2.4/5GHz": ["5ghz", "5 ghz", "2.4/5", "2,4/5"],
    "多猫砂兼容": ["all litter", "any clumping", "all types", "alle streu", "tous types", "todo tipo", "bentonite", "tofu"],
    "静音": ["quiet", "silent", "leise", "silencieux", "silenzioso", "silenciosa"],
}

COUNTRY_STRATEGY = {
    "US": "优先做开放式大入口、多猫与可靠性；AI摄像头仅放高配。当前价格因页面返回CNY不可用，不据此定价。",
    "CA": "主销带建议CAD 249-329；以开放式、安全传感、APP稳定和通用垃圾袋形成中端价值款。",
    "UK": "突出易拆洗、除臭和低噪声；适配英规插头并提供断网可用。当前价格因页面返回CNY不可用。",
    "DE": "强化冗余安全、机械可靠性、可维修和德语APP；公开测试标准比堆叠摄像头更重要。当前价格因页面返回CNY不可用。",
    "FR": "主销带建议EUR 179-259；重点解决噪声、APP连接和防夹，外观保持家居化。",
    "IT": "主销带建议EUR 189-269；把APP配网、离线模式和售后诊断作为首要差异点。",
    "ES": "主销带建议EUR 199-279；大容量、除臭和防夹优先，避免通过专用耗材抬高使用成本。",
}

ROADMAP = [
    ["P0", "生命安全与故障降级", "称重+红外/ToF+电机电流/扭矩冗余；猫在仓内不启动；中途检测立即停机并反向释放；断电断网保持安全", "安全事故会直接摧毁品类信任，且七国标题中安全/防夹已成为高频卖点", "猫存在误启动=0；中途检测停机并反向；传感器单点故障进入禁止自动模式"],
    ["P0", "清洁循环可靠性", "防卡机、防粪团回落、防漏砂；满仓前预警；失败后可恢复并记录故障码", "真实差评集中在清洁、卡机、误报与集便仓；基础循环失败会让全部智能功能失去价值", "连续循环成功率目标≥99.5%；卡机可自动恢复；满仓预警留有至少1天余量"],
    ["P0", "尿液隔离与可维护性", "滚筒、筛网、底盆和集便仓快拆；液体不进入电机、线束和传感器；关键部件可单独更换", "清洁与材质是七国最普遍评论主题之一，英国和意大利负面尤其突出", "用户无工具完成日常拆洗；电气舱防渗；易损件可单独采购"],
    ["P1", "开放式大入口与低门槛", "优先开放式或大开口，低入口，覆盖大猫、老猫和胆小猫；保持防飞砂路径", "开放式/大入口在美加德样本中出现较多，同时可降低封闭仓接受障碍", "入口适配大体型猫；低跨步；猫转身空间通过实体猫测试"],
    ["P1", "密封集便仓与低风险除臭", "机械密封+活性炭/可替换滤材；不依赖臭氧；垃圾袋通用或开放规格", "除臭与集便仓是多国高频且高负面主题，英国、德国、意大利最明显", "关闭状态无明显泄漏；开仓换袋路径不接触污物；滤材寿命和成本透明"],
    ["P1", "稳定APP与本地可用", "2.4/5GHz、蓝牙辅助配网、家庭共享、通知可配置；断网仍可本地清洁和暂停", "APP与连接是美、加、德、法、意的主要负面主题，意大利最突出", "首次配网成功率目标≥95%；离线不影响核心清洁；故障日志可导出"],
    ["P1", "多猫体重与如厕趋势", "用称重和行为数据区分多猫，展示体重/频次趋势并明确非医疗诊断", "多猫是各国常见卖点，但评论显示识别准确性和误报仍有改善空间", "重复称重误差目标≤5%；允许用户修正猫档案；异常只提示趋势不下诊断"],
    ["P1", "猫砂兼容边界", "首发验证膨润土和混合砂；豆腐砂单列筛网与粘壁测试；禁止笼统宣称全砂兼容", "标题中全砂兼容宣称少，说明真实兼容仍是未被充分解决的开发点", "每种声明猫砂完成含水、结团、筛分、粘壁和粉尘测试"],
    ["P2", "摄像头与AI便便识别", "仅在安全、循环和APP达标后增加；提供物理遮挡、隐私存储选项和非订阅基础功能", "摄像头/AI仍是少数高配卖点，不能替代基础可靠性", "关闭摄像头不影响核心功能；AI结论标注置信度；基础记录不强制订阅"],
    ["P2", "自动打包", "作为旗舰模块，不作为首代核心；优先保证通用袋兼容和防夹手动释放", "七国标题中自动打包极少，具备差异化但机械复杂度和耗材风险高", "打包失败不锁死整机；允许手动取袋；耗材价格可公开比较"],
]


def percentile(values, ratio):
    if not values:
        return None
    values = sorted(values)
    return round(values[round((len(values) - 1) * ratio)], 2)


def feature_hits(title):
    text = str(title or "").lower()
    return [name for name, terms in FEATURES.items() if any(term in text for term in terms)]


def display_brand(row):
    brand = str(row.get("brand") or "").strip()
    bad = ("bought in", "app control", "$", "€", "£", "c$", "past month")
    if brand and len(brand) <= 40 and not any(term in brand.lower() for term in bad):
        return brand
    first = str(row.get("title") or "").strip().split(" ", 1)[0].strip("-–—,:()[]")
    generic = {"self", "automatic", "smart", "open", "xxl", "large", "cat", "katzentoilette", "arenero", "lettiera", "litière"}
    return "" if first.lower() in generic or not first else first


def build():
    con = app.connect()
    products = [dict(row) for row in con.execute(
        "SELECT * FROM products WHERE category_path=? ORDER BY country,COALESCE(reviews,0) DESC",
        (CATEGORY,),
    )]
    for row in products:
        classification = app.classify_litter_product_title(row["title"])
        row["classification"] = classification["status"]
        row["classification_reason"] = classification["reason"]
        row["feature_hits"] = feature_hits(row["title"])
        row["brand"] = display_brand(row)
        row["product_url"] = f"https://{app.COUNTRIES[row['country']][1]}/dp/{row['asin']}" if row.get("asin") else row.get("product_url", "")

    qualified = [row for row in products if row["classification"] == "qualified"]
    valid_asins = {(row["country"], row["asin"]) for row in qualified}
    reviews = [dict(row) for row in con.execute("SELECT * FROM reviews ORDER BY country,collected_at DESC")]
    reviews = [row for row in reviews if (row["country"], row["asin"]) in valid_asins]
    for row in reviews:
        row["themes"] = app.review_themes(row["review_title"], row["review_body"], CATEGORY)

    country_rows = []
    theme_rows = []
    feature_rows = []
    for code in COUNTRY_ORDER:
        label, _host, currency, _language = app.COUNTRIES[code]
        raw = [row for row in products if row["country"] == code]
        machines = [row for row in qualified if row["country"] == code]
        local_prices = [row["price"] for row in machines if row["price"] is not None and row["currency"] == currency]
        ratings = [row["rating"] for row in machines if row["rating"] is not None]
        country_reviews = [row for row in reviews if row["country"] == code]
        negative = [row for row in country_reviews if row["rating"] is not None and row["rating"] <= 3]
        theme_counter = Counter(theme for row in country_reviews for theme in row["themes"])
        negative_counter = Counter(theme for row in negative for theme in row["themes"])
        country_rows.append({
            "country": code,
            "label": label,
            "raw_products": len(raw),
            "qualified_products": len(machines),
            "accessories": sum(row["classification"] == "excluded_accessory" for row in raw),
            "manual": sum(row["classification"] == "excluded_manual" for row in raw),
            "unconfirmed": sum(row["classification"] == "unconfirmed" for row in raw),
            "priced_products": len(local_prices),
            "currency": currency,
            "price_p25": percentile(local_prices, 0.25),
            "price_median": percentile(local_prices, 0.5),
            "price_p75": percentile(local_prices, 0.75),
            "average_rating": round(statistics.mean(ratings), 2) if ratings else None,
            "rating_products": len(ratings),
            "review_count": len(country_reviews),
            "review_products": len({row["asin"] for row in country_reviews}),
            "negative_reviews": len(negative),
            "negative_rate": round(len(negative) / len(country_reviews), 4) if country_reviews else None,
            "strategy": COUNTRY_STRATEGY[code],
        })
        for feature in FEATURES:
            count = sum(feature in row["feature_hits"] for row in machines)
            feature_rows.append({"country": code, "label": label, "feature": feature, "count": count, "share": round(count / len(machines), 4) if machines else 0})
        for theme, count in sorted(theme_counter.items(), key=lambda item: (negative_counter[item[0]], item[1]), reverse=True):
            theme_rows.append({
                "country": code,
                "label": label,
                "theme": theme,
                "mentions": count,
                "negative_mentions": negative_counter[theme],
                "negative_share": round(negative_counter[theme] / count, 4) if count else 0,
            })

    conclusions = {
        "analysis_date": "2026-10-26",
        "scope": "US/CA/UK/DE/FR/IT/ES Amazon public search samples",
        "raw_products": len(products),
        "qualified_products": len(qualified),
        "real_reviews": len(reviews),
        "review_products": len({(row['country'], row['asin']) for row in reviews}),
        "management_conclusions": [
            "产品立项应从安全和机械可靠性开始，而不是从摄像头或AI开始。P0未通过时不应上市。",
            "开放式大入口是最适合七国共用的平台方向，可降低大猫、老猫和胆小猫的使用门槛。",
            "APP稳定、除臭集便仓、可拆洗和防漏砂是跨国家的共性价值，必须进入基础款。",
            "摄像头、AI健康识别和自动打包适合高配SKU，不能强制订阅，也不能依赖专用耗材锁定用户。",
            "建议形成基础可靠款、开放式多猫款、AI健康旗舰款三个SKU，而不是一个机型堆满所有功能。",
        ],
        "limitations": [
            "本次商品为Amazon公开搜索页样本，不是完整市场销量排名；没有SellerSprite授权销量时，销量、销售额和增长率保持空白。",
            "美国、英国、德国页面受地区设置影响返回CNY，已清空不匹配价格，因此不输出这三国价格带。",
            "标题功能频次只代表商品页标题宣称，不等同于实验室验证。",
            "评论仅统计与严格合格整机ASIN关联的本地真实评论，排除了早期误抓的喂食器与配件评论。",
        ],
    }

    payload = {
        "meta": conclusions,
        "countries": country_rows,
        "features": feature_rows,
        "themes": theme_rows,
        "roadmap": ROADMAP,
        "products": products,
        "qualified_products": qualified,
        "reviews": reviews,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    now = datetime.now(timezone.utc).isoformat()
    con.execute(
        "DELETE FROM analysis_runs WHERE kind=? AND product_name=? AND source_period=?",
        ("category_product_development", "智能猫砂盆", "Amazon public search and product reviews 2026-10-26"),
    )
    con.execute(
        """INSERT INTO analysis_runs(
             id,kind,product_name,category_path,countries,source_period,sample_count,
             started_at,finished_at,status,conclusions_json,message
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            uuid.uuid4().hex,
            "category_product_development",
            "智能猫砂盆",
            CATEGORY,
            json.dumps(COUNTRY_ORDER),
            "Amazon public search and product reviews 2026-10-26",
            len(qualified),
            now,
            now,
            "COMPLETED",
            json.dumps(conclusions, ensure_ascii=False),
            f"七国产品开发分析完成：700条搜索样本，{len(qualified)}条严格整机，{len(reviews)}条真实评论",
        ),
    )
    con.commit()
    con.close()
    print(json.dumps({"output": str(OUTPUT), **conclusions}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    build()
