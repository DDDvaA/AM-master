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

import app


class AnalysisTests(unittest.TestCase):
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
        self.assertEqual((2, 30, "Amazon 临时拒绝或服务不可用（HTTP 503）"), updates[-1])

    def test_page_issue_identifies_amazon_verification(self):
        self.assertIn("风控验证页", app.detect_page_issue(b"<meta http-equiv='refresh' content='bm-verify=abc'>"))

    def test_csv_import_and_excel_export(self):
        payload = b"Country,Category,ASIN,Title,Price,Currency,Units,Revenue,Growth,Rating,Reviews\nDE,Pet > Cat > Automatic feeder,B012345678,Two hopper WiFi feeder,79.99,EUR,240,19197.6,22,4.5,120\n"
        imported = app.import_rows("research.csv", payload)
        self.assertEqual(1, imported)
        con = app.connect()
        row = con.execute("SELECT country,asin,units,revenue FROM products").fetchone()
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
