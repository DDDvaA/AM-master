import os
import tempfile
import unittest
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

TEMP_DATA = tempfile.TemporaryDirectory()
os.environ["AM_MASTER_DATA_DIR"] = TEMP_DATA.name
os.environ["AM_MASTER_AMAZON_BROWSER_RECOVERY"] = "0"

import app
import amazon_browser_connector
import amazon_review_connector
import sellersprite_connector


class AnalysisTests(unittest.TestCase):
    def test_amazon_browser_recognizes_localized_and_link_based_results(self):
        self.assertTrue(amazon_browser_connector._is_challenge("Geben Sie die Zeichen ein validateCaptcha"))
        self.assertTrue(amazon_browser_connector._same_search_page("https://www.amazon.de/s?k=futter", "https://www.amazon.de/s?k=feeder"))
        markup = amazon_browser_connector._cards_to_markup([{"asin":"B000000001", "title":"Cat & Dog feeder", "href":"https://www.amazon.de/dp/B000000001", "image":"https://img.example/1.jpg", "price":"49,99"}])
        parser = app.AmazonSearchParser("https://www.amazon.de")
        parser.feed(markup)
        self.assertEqual("B000000001", parser.items[0]["asin"])
        self.assertEqual("Cat & Dog feeder", parser.items[0]["title"])

    def test_sellersprite_card_parser_extracts_authorized_metrics(self):
        text = "A+ V AC Yuposl Automatic Cat Feeder, 3L Cat Food Dispenser B0FCM74WM2 FBA 卖家: 2 卖家: Petfit Home CA 品牌: Yuposl #204 in Pet Supplies #1 in Automatic Cat Feeders 销量(父): 2,023 子体销量: 1K+ 销售额: C$91,075 变体数: 7 价格: C$47.99 评分/评分数: 4.3 / 4,760 上架时间: 2025-08-14"
        row = sellersprite_connector.parse_card_text(text, "https://www.amazon.ca/dp/B0FCM74WM2")
        self.assertEqual("B0FCM74WM2", row["asin"])
        self.assertEqual("Yuposl", row["brand"])
        self.assertEqual(2023.0, row["units"])
        self.assertEqual(91075.0, row["revenue"])
        self.assertEqual(47.99, row["price"])
        self.assertEqual(4.3, row["rating"])
        self.assertEqual(4760.0, row["reviews"])
        self.assertEqual(204.0, row["bsr_rank"])

    def test_sellersprite_url_requires_supported_market(self):
        _parsed, market = sellersprite_connector.validate_sellersprite_url("https://www.sellersprite.com/v3/competitor-lookup/?market=CA&page=1")
        self.assertEqual("CA", market)
        with self.assertRaises(ValueError):
            sellersprite_connector.validate_sellersprite_url("https://example.com/v3/competitor-lookup/?market=CA")

    def test_feature_extraction_is_deterministic(self):
        result = app.extract_features("双粮仓 WiFi 定时定量喂食，摄像头支持夜视")
        self.assertTrue(result["双仓/多仓"]["present"])
        self.assertTrue(result["Wi-Fi/APP"]["present"])
        self.assertTrue(result["夜视"]["present"])
        self.assertFalse(result["备用电源"]["present"])

    def test_opportunity_tags_need_metrics(self):
        rows = [
            {"country":"DE","category_path":"pet > cat > feeder","units":100,"revenue":1000,"growth":25,"price":90},
            {"country":"DE","category_path":"pet > cat > feeder","units":20,"revenue":250,"growth":0,"price":20},
            {"country":"CA","category_path":"pet > cat > feeder","units":None,"revenue":None,"growth":None,"price":None},
        ]
        tagged = app.opportunity_tags(rows)
        self.assertIn("高增长", tagged[0]["opportunity_tags"])
        self.assertIn("流量款", tagged[0]["opportunity_tags"])
        self.assertEqual([], tagged[2]["opportunity_tags"])

    def test_review_theme_detection_and_summary(self):
        themes = app.review_themes("WiFi timeout", "The app goes offline and the portion is too large")
        self.assertIn("APP与连接", themes)
        self.assertIn("份量准确", themes)
        app.save_reviews([{
            "country":"DE","asin":"B012345678","product_title":"Feeder","review_id":"R1",
            "rating":2.0,"review_title":"App timeout","review_body":"WiFi connection failed and portion too large",
            "review_date_text":"Reviewed in Germany","verified":1,"helpful_count":3,"reviewer":"A",
            "review_url":"https://www.amazon.de/gp/customer-reviews/R1","source":"Amazon product reviews","collected_at":"2026-10-26T00:00:00+00:00",
        }])
        summary = next(item for item in app.review_summary("DE") if item["country"] == "DE")
        self.assertEqual(1, summary["sample_count"])
        self.assertEqual(1, summary["negative_count"])
        self.assertTrue(any(item["theme"] == "APP与连接" for item in summary["themes"]))

    def test_public_product_review_parser(self):
        markup = '''<div data-hook="review"><a data-csa-c-slot-id="customer_review-RABC123_1_profile"><span class="a-profile-name">Buyer</span></a><i data-hook="review-star-rating"><span class="a-icon-alt">2 out of 5 stars</span></i><a href="/portal/customer-reviews/srp/-/RABC123"><h5 data-hook="reviewTitle">Connection issue</h5></a><span data-hook="review-date">Reviewed in Germany</span><span data-hook="avp-badge">Verified Purchase</span><div data-hook="reviewRichContentContainer"><p><span>WiFi timeout and portion too large.</span></p></div></div>'''
        rows = amazon_review_connector.parse_public_product_reviews(markup, "https://www.amazon.de")
        self.assertEqual(1, len(rows))
        self.assertEqual("RABC123", rows[0]["review_id"])
        self.assertEqual("Connection issue", rows[0]["title"])
        self.assertIn("WiFi timeout", rows[0]["body"])

    def test_review_product_selection_prefers_bsr(self):
        base = {"country":"IT","category_path":"Pet > Cat > Feeder","source_date":"2026-10-26T00:00:00+00:00","brand":"Brand","price":50,"currency":"EUR","units":None,"revenue":None,"growth":None,"rating":4.2,"reviews":100,"image_url":"","source":"Amazon public search"}
        app.save_products([{**base,"asin":"B011111111","title":"Popular feeder","bsr_rank":None,"product_url":"https://www.amazon.it/dp/B011111111"},{**base,"asin":"B022222222","title":"BSR feeder","bsr_rank":5,"reviews":10,"product_url":"https://www.amazon.it/dp/B022222222"}])
        chosen = app.choose_review_products("IT","Pet > Cat > Feeder",2)
        self.assertEqual("B022222222", chosen[0]["asin"])

    def test_review_product_selection_excludes_litter_accessories(self):
        base = {"country":"DE","category_path":"Pet Supplies > Cats > Litter Boxes","source_date":"2026-10-26T00:00:00+00:00","brand":"Brand","price":200,"currency":"EUR","units":None,"revenue":None,"growth":None,"rating":4.2,"reviews":100,"image_url":"","source":"Amazon public search","bsr_rank":None}
        app.save_products([
            {**base,"asin":"B033333333","title":"100 Bags for Automatic Litter Box Replacement Liner","reviews":5000,"product_url":"https://www.amazon.de/dp/B033333333"},
            {**base,"asin":"B044444444","title":"Selbstreinigende Katzentoilette mit APP und Sicherheitssensor","reviews":200,"product_url":"https://www.amazon.de/dp/B044444444"},
        ])
        chosen = app.choose_review_products("DE","Pet Supplies > Cats > Litter Boxes",1)
        self.assertEqual("B044444444", chosen[0]["asin"])

    def test_litter_review_themes_are_detected(self):
        themes = app.review_themes("Unsafe cycle", "The cat was nearly pinched, litter leaks everywhere and the waste drawer smells", "Pet Supplies > Cats > Litter Boxes")
        self.assertIn("安全与防夹", themes)
        self.assertIn("漏砂与带砂", themes)
        self.assertIn("除臭与集便仓", themes)
        self.assertNotIn("出粮可靠性", themes)

    def test_litter_product_classification_requires_automated_machine(self):
        self.assertEqual(
            "qualified",
            app.classify_litter_product_title("Self-Cleaning Smart Litter Box with App")["status"],
        )
        self.assertEqual(
            "excluded_accessory",
            app.classify_litter_product_title("100 Waste Bags for Automatic Litter Box")["status"],
        )
        self.assertEqual(
            "excluded_accessory",
            app.classify_litter_product_title("Deodorization Box Compatible with Self-Cleaning Cat Litter Box")["status"],
        )
        self.assertEqual(
            "excluded_accessory",
            app.classify_litter_product_title("Petivity Smart Litter Box Monitor")["status"],
        )
        self.assertEqual(
            "excluded_manual",
            app.classify_litter_product_title("Omega Paw Roll 'n Clean Self-Cleaning Litter Box")["status"],
        )
        self.assertEqual(
            "unconfirmed",
            app.classify_litter_product_title("Large Open Cat Litter Box")["status"],
        )
        self.assertEqual(
            "qualified",
            app.classify_litter_product_title("Automatic Self-Cleaning Litter Box with Waste Bags and Mat")["status"],
        )
        self.assertEqual(
            "excluded_accessory",
            app.classify_litter_product_title("80 Count Waste Bags for Self-Cleaning Litter Box")["status"],
        )
        self.assertEqual(
            "excluded_accessory",
            app.classify_litter_product_title("Self-Cleaning Cat Litter Box Tray Refills 3-Pack")["status"],
        )

    def test_country_mapping(self):
        self.assertEqual("CA", app.canonical_country("加拿大"))
        self.assertEqual("DE", app.canonical_country("DE"))

    def test_public_search_parser_extracts_visible_fields(self):
        markup = '''<div data-component-type="s-search-result" data-asin="B012345678"><h2><span class="a-size-base-plus">Sample feeder</span></h2><a class="a-link-normal s-link-style" href="/dp/B012345678"><img src="https://img.example/p.jpg"></a><span class="a-price-whole">49</span><span class="a-icon-alt">4.4 out of 5 stars</span><span class="s-underline-text">321</span></div>'''
        parser = app.AmazonSearchParser("https://www.amazon.ca")
        parser.feed(markup)
        self.assertEqual(1, len(parser.items))
        self.assertEqual("B012345678", parser.items[0]["asin"])
        self.assertEqual("Sample feeder", parser.items[0]["title"])
        self.assertEqual("https://www.amazon.ca/dp/B012345678", parser.items[0]["product_url"])
        self.assertEqual(49.0, parser.items[0]["price"])
        self.assertEqual(4.4, parser.items[0]["rating"])
        self.assertEqual(321.0, parser.items[0]["reviews"])

    def test_public_search_parser_ignores_duplicate_metrics_and_expands_compact_reviews(self):
        markup = '''<div data-component-type="s-search-result" data-asin="B012345671"><h2><span>Smart litter box</span></h2><a href="/dp/B012345671"></a><span class="a-price-whole">80</span><span class="a-price-whole">80</span><span class="a-icon-alt">4.5 out of 5 stars</span><span class="a-icon-alt">4.5 out of 5 stars</span><span class="s-underline-text">1.2K</span><span class="s-underline-text">1.2K</span></div>'''
        parser = app.AmazonSearchParser("https://www.amazon.com")
        parser.feed(markup)
        self.assertEqual(80.0, parser.items[0]["price"])
        self.assertEqual(4.5, parser.items[0]["rating"])
        self.assertEqual(1200.0, parser.items[0]["reviews"])

    def test_public_search_parser_reads_actual_currency_and_localized_thousands(self):
        markup = '''<div data-component-type="s-search-result" data-asin="B012345672"><h2><span>Automatic litter box</span></h2><a href="/dp/B012345672"></a><span class="a-offscreen">CNY 1,600.65</span><span class="a-price-whole">1,600</span><span class="a-price-fraction">65</span><span class="a-icon-alt">4,2 de 5 estrellas</span><span class="s-underline-text">1,7 mil</span></div>'''
        parser = app.AmazonSearchParser("https://www.amazon.es")
        parser.feed(markup)
        self.assertEqual(1600.65, parser.items[0]["price"])
        self.assertEqual("CNY", parser.items[0]["currency"])
        self.assertEqual(4.2, parser.items[0]["rating"])
        self.assertEqual(1700.0, parser.items[0]["reviews"])

    def test_public_search_parser_accepts_modern_h2_title(self):
        markup = '''<div data-component-type="s-search-result" data-asin="B012345679"><h2><span>Modern title markup</span></h2><a href="/dp/B012345679"><img src="https://img.example/new.jpg"></a></div>'''
        parser = app.AmazonSearchParser("https://www.amazon.com")
        parser.feed(markup)
        self.assertEqual("Modern title markup", parser.items[0]["title"])

    def test_product_badge_does_not_replace_h2_title(self):
        markup = '''<div data-component-type="s-search-result" data-asin="B012345670"><a aria-label="Amazon's Choice: Overall Pick" href="/dp/B012345670">Badge</a><a class="s-link-style" href="/dp/B012345670"><h2 aria-label="Real feeder title"><span>Real feeder title</span></h2></a></div>'''
        parser = app.AmazonSearchParser("https://www.amazon.com")
        parser.feed(markup)
        self.assertEqual("Real feeder title", parser.items[0]["title"])

    def test_product_deduplication_prefers_asin_then_url(self):
        rows = [
            {"asin":"B012345678", "title":"First", "product_url":"https://www.amazon.com/dp/B012345678?ref=x"},
            {"asin":"B012345678", "title":"Changed title", "product_url":"https://www.amazon.com/dp/B012345678"},
            {"asin":"", "title":"URL product", "product_url":"https://www.amazon.com/dp/B087654321?tag=test"},
            {"asin":"", "title":"Same URL product", "product_url":"https://www.amazon.com/dp/B087654321/ref=something"},
        ]
        self.assertEqual(2, len(app.deduplicate_products(rows)))

    def test_amazon_search_collects_up_to_100_unique_products(self):
        class Response:
            def __init__(self, body, url): self.body, self.url = body, url
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def read(self): return self.body
            def geturl(self): return self.url

        pages = []
        def fake_urlopen(request, timeout=25):
            page = int(urllib.parse.parse_qs(urllib.parse.urlparse(request.full_url).query)["page"][0])
            pages.append(page)
            start = (page - 1) * 30 + 1
            markup = "".join(
                f'<div data-component-type="s-search-result" data-asin="B{number:09d}"><h2><span>Product {number}</span></h2><a href="/dp/B{number:09d}"><img src="https://img.example/{number}.jpg"></a></div>'
                for number in range(start, start + 30)
            )
            return Response(markup.encode(), request.full_url)

        with patch("app.urllib.request.urlopen", side_effect=fake_urlopen), patch("app.time.sleep"):
            products = app.amazon_search("US", "feeder", "Pet > Feeders")
        self.assertEqual(100, len(products))
        self.assertEqual([1, 2, 3, 4], pages)
        self.assertEqual(100, len({app.product_identity(row) for row in products}))

    def test_amazon_search_keeps_partial_results_when_next_page_is_blocked(self):
        class Response:
            def __init__(self, body, url): self.body, self.url = body, url
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def read(self): return self.body
            def geturl(self): return self.url

        markup = "".join(
            f'<div data-component-type="s-search-result" data-asin="B{number:09d}"><h2><span>Product {number}</span></h2><a href="/dp/B{number:09d}"></a></div>'
            for number in range(1, 31)
        ).encode()
        updates = []
        def fake_urlopen(request, timeout=25):
            page = int(urllib.parse.parse_qs(urllib.parse.urlparse(request.full_url).query)["page"][0])
            if page == 1:
                return Response(markup, request.full_url)
            raise urllib.error.HTTPError(request.full_url, 503, "Service Unavailable", {}, None)

        with patch("app.urllib.request.urlopen", side_effect=fake_urlopen), patch("app.time.sleep"):
            products = app.amazon_search("ES", "feeder", "Pet > Feeders", lambda page, count, added, warning: updates.append((page, count, warning)))
        self.assertEqual(30, len(products))
        self.assertIn("HTTP 503", updates[-1][2])

    def test_amazon_search_retries_503_then_recovers(self):
        class Response:
            def __init__(self, body, url): self.body, self.url = body, url
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def read(self): return self.body
            def geturl(self): return self.url

        calls = 0
        markup = b'<div data-component-type="s-search-result" data-asin="B012345699"><h2><span>Recovered feeder</span></h2><a href="/dp/B012345699"></a></div>'
        def fake_urlopen(request, timeout=25):
            nonlocal calls
            calls += 1
            if calls < 3:
                raise urllib.error.HTTPError(request.full_url, 503, "Service Unavailable", {}, None)
            return Response(markup, request.full_url)

        with patch("app.urllib.request.urlopen", side_effect=fake_urlopen), patch("app.time.sleep"):
            products = app.amazon_search("CA", "recovery feeder", "Pet > Recovery")
        self.assertEqual("B012345699", products[0]["asin"])
        self.assertGreaterEqual(calls, 3)

    def test_amazon_search_uses_page_cache_after_empty_response(self):
        class EmptyResponse:
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def read(self): return b""
            def geturl(self): return "https://www.amazon.co.uk/s?k=cached"

        markup = b'<div data-component-type="s-search-result" data-asin="B012345698"><h2><span>Cached feeder</span></h2><a href="/dp/B012345698"></a></div>'
        app.save_amazon_page_cache("UK", "cached feeder", 1, "https://www.amazon.co.uk/s?k=cached", markup)
        with patch("app.urllib.request.urlopen", return_value=EmptyResponse()), patch("app.time.sleep"):
            products = app.amazon_search("UK", "cached feeder", "Pet > Cached")
        self.assertEqual("B012345698", products[0]["asin"])
        self.assertEqual("Amazon cached public search", products[0]["source"])

    def test_bsr_category_cache_is_selected_before_search_results(self):
        base = {"country":"FR", "category_path":"Pet > Cat > Feeder", "source_date":"2026-10-23T00:00:00+00:00", "title":"Authorized feeder", "brand":"Brand", "price":79.0, "currency":"EUR", "units":300.0, "revenue":23700.0, "growth":None, "rating":4.4, "reviews":100.0, "bsr_rank":12, "image_url":"", "product_url":"https://www.amazon.fr/dp/B077777777", "asin":"B077777777"}
        app.save_products([{**base, "source":"SellerSprite authorized browser"}])
        rows = app.load_bsr_category_products("FR", "Pet > Cat > Feeder")
        self.assertEqual(1, len(rows))
        self.assertEqual("B077777777", rows[0]["asin"])
        search_rows = [
            {**base, "source":"Amazon public search", "title":"Duplicate search version", "bsr_rank":None},
            {**base, "source":"Amazon public search", "asin":"B077777778", "product_url":"https://www.amazon.fr/dp/B077777778", "title":"Search-only feeder", "bsr_rank":None},
        ]
        merged = app.merge_bsr_then_search(rows, search_rows)
        self.assertEqual(["B077777777", "B077777778"], [row["asin"] for row in merged])
        self.assertEqual("SellerSprite authorized browser", merged[0]["source"])

    def test_page_issue_identifies_amazon_verification(self):
        self.assertIn("风控验证页", app.detect_page_issue(b"<meta http-equiv='refresh' content='bm-verify=abc'>"))

    def test_csv_import_and_excel_export(self):
        payload = b"Country,Category,ASIN,Title,Price,Currency,Units,Revenue,Growth,Rating,Reviews\nDE,Pet > Cat > Automatic feeder,B012345678,Two hopper WiFi feeder,79.99,EUR,240,19197.6,22,4.5,120\n"
        imported = app.import_rows("research.csv", payload)
        self.assertEqual(1, imported)
        con = app.connect()
        row = con.execute("SELECT country,asin,units,revenue FROM products WHERE asin='B012345678'").fetchone()
        con.close()
        self.assertEqual(("DE", "B012345678", 240.0, 19197.6), tuple(row))
        workbook = app.export_xlsx("Pet > Cat > Automatic feeder")
        self.assertGreater(len(workbook), 1000)

    def test_save_products_deduplicates_and_preserves_sales_metrics(self):
        base = {"country":"US", "category_path":"Pet > Feeders", "source_date":"2026-10-23T00:00:00+00:00", "asin":"B099999999", "title":"Imported feeder", "brand":"Brand", "price":89.0, "currency":"USD", "units":200.0, "revenue":17800.0, "growth":21.0, "rating":4.3, "reviews":80.0, "image_url":"", "product_url":"https://www.amazon.com/dp/B099999999"}
        app.save_products([{**base, "source":"导入:research.csv"}])
        app.save_products([{**base, "source":"Amazon public search", "source_date":"2026-10-24T00:00:00+00:00", "title":"Updated public title", "units":None, "revenue":None, "growth":None, "rating":4.4}])
        con = app.connect()
        rows = con.execute("SELECT source,title,units,revenue,growth,rating FROM products WHERE country='US' AND asin='B099999999'").fetchall()
        con.close()
        self.assertEqual(1, len(rows))
        self.assertEqual(("导入:research.csv", "Updated public title", 200.0, 17800.0, 21.0, 4.4), tuple(rows[0]))


class HttpValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), app.ExportHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_static_traversal_is_rejected(self):
        request = urllib.request.Request(f"{self.base_url}/static/../app.py")
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request)
        self.assertEqual(404, error.exception.code)

    def test_search_requires_country(self):
        payload = json.dumps({"keyword": "feeder", "countries": []}).encode()
        request = urllib.request.Request(f"{self.base_url}/api/search", data=payload, headers={"Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request)
        self.assertEqual(400, error.exception.code)

    def test_analysis_requires_country(self):
        payload = json.dumps({"product_name": "Feeder", "product_text": "WiFi feeder", "countries": []}).encode()
        request = urllib.request.Request(f"{self.base_url}/api/analyze", data=payload, headers={"Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request)
        self.assertEqual(400, error.exception.code)

    def test_local_research_workflow_and_excel_export(self):
        csv_data = b"Country,Category,ASIN,Title,Price,Currency,Units,Revenue,Growth\nDE,Pet > Cat > Feeders,EXAMPLE0001,Dual hopper WiFi feeder,99,EUR,320,31680,24.5\n"
        request = urllib.request.Request(f"{self.base_url}/api/import", data=csv_data, headers={"Content-Type": "application/octet-stream", "X-File-Name": "test.csv"})
        with urllib.request.urlopen(request) as response:
            self.assertEqual(1, json.loads(response.read())["imported"])

        with urllib.request.urlopen(f"{self.base_url}/api/products?country=DE") as response:
            products = json.loads(response.read())["items"]
        self.assertTrue(any(row["asin"] == "EXAMPLE0001" for row in products))

        analysis = json.dumps({"product_name": "Test feeder", "product_text": "双粮仓 WiFi 定时喂食", "category_path": "Pet > Cat > Feeders", "countries": ["DE"]}).encode()
        request = urllib.request.Request(f"{self.base_url}/api/analyze", data=analysis, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request) as response:
            self.assertTrue(json.loads(response.read())["id"])

        with urllib.request.urlopen(f"{self.base_url}/api/export.xlsx?category=Pet%20%3E%20Cat%20%3E%20Feeders") as response:
            self.assertEqual("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", response.headers["Content-Type"])
            self.assertGreater(len(response.read()), 1000)


if __name__ == "__main__":
    unittest.main()
