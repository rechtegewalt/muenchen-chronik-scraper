import re

import dataset
import get_retries
from bs4 import BeautifulSoup
import dateparser

db = dataset.connect("sqlite:///data.sqlite")

tab_incidents = db["incidents"]
tab_sources = db["sources"]
tab_chronicles = db["chronicles"]


tab_chronicles.upsert(
    {
        "iso3166_1": "DE",
        "iso3166_2": "DE-BY",
        "region": "München",
        "chronicler_name": "München Chronik",
        "chronicler_description": "Durch die Recherche- und Dokumentationsarbeiten der Fachinformationsstelle Rechtsextremismus in München (FIRM) und der antifaschistischen Informations-, Dokumentations- und Archivstelle München e. V. (a.i.d.a) sowie durch die Arbeit der Opferberatungs- und Antidiskriminierungsstelle BEFORE, aber auch auf Grund von Zusendungen von weiteren Münchner Organisationen und Einzelpersonen entsteht ein (unvollständiges) Bild davon, welche Aktivitäten rechter Gruppen und diskriminierende Vorfälle es in München (sowohl in der Stadt, als auch im Landkreis) gibt.",
        "chronicler_url": "https://muenchen-chronik.de",
        "chronicle_source": "https://muenchen-chronik.de/chronik/",
    },
    ["chronicler_name"],
)


BASE_URL = "https://muenchen-chronik.de/chronik/"

location_options = {}
motiv_options = {}
handlung_options = {}
kontext_options = {}


def fix_date_typo_missing(x):
    """"""
    if not ":" in x:
        x = re.sub(r"(\d{1,2}\.\d{1,2}\.\d\d) ", r"\1: ", x)
    return x


def ends_with_date_like(x):
    regex = re.compile(r".*\d{1,2}\.\d{1,2}\.\d\d")
    return re.match(regex, x.strip()) is not None


def fetch(url):
    res = get_retries.get(url, verbose=True, max_backoff=128)
    if res is None:
        return None
    html_content = res.text
    soup = BeautifulSoup(html_content, "lxml")
    return soup


def fetch_json(url):
    return get_retries.get(url, verbose=True, max_backoff=128).json()


# https://stackoverflow.com/a/7160778/4028896
def is_url(s):
    regex = re.compile(
        r"^(?:http|ftp)s?://"  # http:// or https://
        r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|"  # domain...
        r"localhost|"  # localhost...
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # ...or ip
        r"(?::\d+)?"  # optional port
        r"(?:/?|[/?]\S+)$",
        re.IGNORECASE,
    )
    return re.match(regex, s) is not None


geo_data = {}


def setup_geolocations():
    """
    There are sometimes multiple locations for one incident. FIXME
    It's also not guaranteed that there is at least one location for each incident.
    """
    jsondata = fetch_json(
        "https://muenchen-chronik.de/maps/geojson/layer/2,3,11,12,13,18,19,20,21/?full=no&full_icon_url=no&listmarkers=0"
    )
    for x in jsondata["features"]:
        soup = BeautifulSoup(x["properties"]["text"], "lxml")
        link = soup.find("a").get("href").replace("http://", "").replace("https://", "")

        # assert not link in geo_data, link + str(geo_data)
        geo_data[link] = {
            "longitude": x["geometry"]["coordinates"][0],
            "latitude": x["geometry"]["coordinates"][1],
        }


def process_report(report, url):
    """
    https://dateparser.readthedocs.io/en/latest/settings.html#handling-incomplete-dates
    """
    header = report.select_one(".entry-header").get_text()
    if " – " in header:
        header = header.split(" – ")
        date, title = header[:-1], header[-1]
        date = " ".join(date)
        date = dateparser.parse(
            date,
            languages=["de"],
            settings={
                "STRICT_PARSING": True,
                "REQUIRE_PARTS": ["day", "month", "year"],
            },
        )

        if date is None:
            date2 = dateparser.parse(
                header[0],
                languages=["de"],
                settings={
                    "STRICT_PARSING": True,
                    "REQUIRE_PARTS": ["day", "month", "year"],
                },
            )
            if date2 is not None:
                date = date2
                title = " – ".join(header[1:])
            else:
                date3 = dateparser.parse(
                    header[0].split("/")[0],
                    languages=["de"],
                    settings={
                        "STRICT_PARSING": True,
                        "REQUIRE_PARTS": ["day", "month", "year"],
                    },
                )
                if date3 is not None:
                    date = date3
                else:
                    if not "/" in header[0]:
                        # FIXME
                        print("skip for now")
                        print(report)
                    else:
                        date4 = dateparser.parse(
                            header[0].split("/")[1],
                            languages=["de"],
                            settings={
                                "STRICT_PARSING": True,
                                "REQUIRE_PARTS": ["day", "month", "year"],
                            },
                        )
                        if date4 is not None:
                            date = date4
                        else:
                            raise ValueError("failed date parsing, please fix")
    else:
        date, title = header.split("2017")
        date += "2017"
        date = dateparser.parse(date, languages=["de"])

    title = title.strip()
    description = report.select_one(".entry-content").get_text(separator="\n").strip()
    rg_id = url

    tags = []
    sources = []
    for x in report.select(".smallinfo"):
        x_txt = x.get_text()

        if x_txt.startswith("Quelle:"):
            for s in x_txt.split(","):
                sources.append({"name": s, "rg_id": rg_id})
        elif x_txt.startswith("Schlagworte:"):
            for t in x.select("a"):
                tags.append(t.get_text())

    locations = ["München"]
    motives = []
    contexts = []
    factums = []
    for x in report.get("class"):
        if x in location_options:
            locations.append(location_options[x])
        if x in motiv_options:
            motives.append(motiv_options[x])
        if x in kontext_options:
            contexts.append(kontext_options[x])
        if x in handlung_options:
            factums.append(handlung_options[x])

    if url.replace("https://", "") in geo_data:
        geoloc = geo_data[url.replace("https://", "")]
    else:
        print("no geolocation found")
        geoloc = {}

    data = dict(
        chronicler_name="München Chronik",
        tags=", ".join(tags),
        motives=", ".join(motives),
        contexts=", ".join(contexts),
        factums=", ".join(factums),
        city=", ".join(locations),
        description=description,
        title=title,
        date=date,
        rg_id=rg_id,
        url=url,
        **geoloc
    )

    # print(data)

    tab_incidents.upsert(data, ["rg_id"])

    for s in sources:
        tab_sources.upsert(s, ["rg_id", "name", "url"])


def process_page(page):
    next_link = page.select_one(".nextpostslink")
    if next_link is None:
        next_link = None
    else:
        next_link = next_link.get("href")

    for row in page.select(".entry-content a"):
        url = row.get("href")
        soup = fetch(url)
        process_report(soup.select_one("article.post"), url)
    return next_link

    # next_link = page.select_one("li.pager-next a")

    # if next_link is None:
    #     return None

    # return "https://response-hessen.de" + next_link.get("href")


setup_geolocations()
print(len(geo_data))

next_url = BASE_URL
next_url = "https://muenchen-chronik.de/chronik/"
soup = fetch(next_url)

location_options = {}
motiv_options = {}
handlung_options = {}
kontext_options = {}

for o in soup.select(".sf-field-category option"):
    if o.get("value") == "":
        continue
    label = o.get_text()
    value = "category-" + o.get("value")
    location_options[value] = label

for o in soup.select(".sf-field-taxonomy-motiv option"):
    if o.get("value") == "":
        continue
    label = o.get_text()
    value = "motiv-" + o.get("value")
    motiv_options[value] = label

for o in soup.select(".sf-field-taxonomy-handlung option"):
    if o.get("value") == "":
        continue
    label = o.get_text()
    value = "handlung-" + o.get("value")
    handlung_options[value] = label

for o in soup.select(".sf-field-taxonomy-kontext option"):
    if o.get("value") == "":
        continue
    label = o.get_text()
    value = "kontext-" + o.get("value")
    kontext_options[value] = label

print(location_options)
print(motiv_options)
print(handlung_options)
print(kontext_options)

while True:
    print(next_url)
    next_url = process_page(soup)
    if next_url is None:
        break
    soup = fetch(next_url)
