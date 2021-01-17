# München Chronik Scraper

Scraping right-wing incidents in Munich (_München_), Germany as monitored on <https://muenchen-chronik.de/chronik/>.

-   Website: <https://muenchen-chronik.de/chronik/>
-   Data: <https://morph.io/rechtegewalt/muenchen-chronik-scraper>

## Usage

For local development:

-   Install [poetry](https://python-poetry.org/)
-   `poetry install`
-   `poetry run python scraper.py`

For Morph:

-   `poetry export -f requirements.txt --output requirements.txt`
-   commit the `requirements.txt`
-   modify `runtime.txt`

## Morph

This is scraper runs on [morph.io](https://morph.io). To get started [see the documentation](https://morph.io/documentation).

## License

MIT
