import os
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()
