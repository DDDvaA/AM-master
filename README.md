# AM master

AM master is a local-first, tokenless marketplace research workspace. It searches public Amazon listing pages across seven marketplaces, stores snapshots in local SQLite, imports authorized sales exports, identifies sample-relative opportunity candidates, compares pasted product specifications with observed listing evidence, displays product images and exports an Excel workbook.

It does not call an LLM or send pasted product specifications to a cloud model. Public listing pages generally do not expose dependable units or revenue. Those fields are never fabricated: import them from SellerSprite or another licensed source and keep the source name in the workbook.

## Start on Windows

1. Install Python 3.10 or newer.
2. Run `setup_windows.bat` once.
3. Run `start_app.bat`. The local interface opens at `http://127.0.0.1:8777`.
4. The default database and cached page snapshots are stored in `D:\AM-master-data`. Set `AM_MASTER_DATA_DIR` to choose another directory.

On macOS/Linux, create a virtual environment, install `requirements.txt`, set `AM_MASTER_DATA_DIR`, and run `python app.py`.

## Research workflow

1. Enter a three-level category path and a product name or search phrase.
2. Select one or more countries and start a search. Each marketplace continues through result pages until it has up to 100 unique products or no additional products are available. The interface reports page and deduplicated-product progress. A blocked page is recorded as a failure; AM master does not bypass login walls, CAPTCHAs, or access controls.
3. Import SellerSprite or internal research exports from **Local Data**. CSV/XLSX headers are mapped by common English and Chinese labels. Include a country column using US, CA, UK, DE, FR, IT, or ES.
4. Products can be tagged as high-growth (growth >= 20%), traffic candidates (units or revenue >= the within-sample 75th percentile), or high-price candidates (price >= the within-sample 75th percentile). These are screening rules, not proof of net profit. Net margin requires cost, fees, ads, returns, and tax inputs.
5. Paste product information into **Product Fit**. The local rules detect a controlled set of features and compare them with collected listing titles. Missing title evidence is marked unverified, not treated as proof a competitor lacks the feature.
6. Export the current local dataset and recent feature comparisons to Excel.

## SellerSprite authorized browser connector

AM master can open a visible dedicated Edge session for SellerSprite. Enter credentials only in SellerSprite's own login page; AM master does not receive or store the password. The local browser profile is stored under the configured data directory. Paste an authorized competitor or market-results URL to read up to 100 unique visible products and save the displayed units, revenue, price, rating and review count. The connector does not click paid export actions, bypass CAPTCHAs, or continue past an access-control challenge.

## Import columns

Recognized columns include country, category path (three levels recommended), ASIN/product ID, title, brand, price, currency, monthly units, monthly revenue, growth percent, rating, review count, image URL, and product URL. Sales metrics retain the values supplied in the imported file; note the source period and measurement basis in the source file and do not combine different periods without normalizing them.

## Data sources and extensions

- **Amazon public search pages:** optional, user-triggered listing metadata only. Availability, page structure, and access rules vary. The app stores the raw response for troubleshooting and stops when the page cannot be parsed.
- **SellerSprite / licensed research exports:** use the account and export rights held by the operator. Import the downloaded CSV/XLSX locally. Automated authenticated browser export can be added as a separate opt-in connector without sharing browser profiles or credentials.
- **Amazon Selling Partner API:** an optional future adapter for accounts with the required authorization and marketplace permissions. It is not required for the local import workflow.

Potential components to evaluate for a future authorized connector: [Microsoft Playwright Python](https://github.com/microsoft/playwright-python) for browser automation, and Amazon's official [Selling Partner API documentation](https://developer-docs.amazon.com/sp-api/). Do not add CAPTCHA solving, proxy rotation intended to evade limits, credential harvesting, or access-control bypass.

## Data and privacy

The app binds only to `127.0.0.1`. Database, imported exports, and raw page snapshots stay in the configured local data directory. Do not publish that directory. A public GitHub checkout contains source code only. No analytics, telemetry, model API, or cloud sync is configured.

## Known limitations

- Search results can be blocked or change markup. Failed countries are reported; no anti-bot bypass is attempted.
- Public listing title, price, rating, review count, and images are not a substitute for SellerSprite monthly sales estimates.
- Feature extraction is deterministic keyword matching. It is a review aid, not semantic understanding or a legal claim substantiation system.
- “Profit candidate” currently means a high price relative to the selected sample, not verified contribution margin.
- Image display is side-by-side evidence. It does not claim pixel-perfect geometric or visual similarity scoring.

## License

MIT. See `LICENSE`.
