import os
import tempfile
import unittest
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

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
