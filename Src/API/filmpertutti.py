from tmdbv3api import TMDb, Movie, TV
from bs4 import BeautifulSoup, SoupStrainer
import string
import re
import dateparser
from Src.Utilities.convert import get_TMDb_id_from_IMDb_id
from Src.Utilities.info import get_info_tmdb, is_movie, get_info_imdb
from Src.Utilities.convert_date import convert_US_date
import Src.Utilities.config as config
import urllib.parse
from functools import lru_cache

FT_DOMAIN = config.FT_DOMAIN
WOA = 0

# Some basic headers
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.10; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3',
    'Accept-Language': 'en-US,en;q=0.5'
}

# Map months to check if date = date
month_mapping = {
    'Jan': 'Gennaio', 'Feb': 'Febbraio', 'Mar': 'Marzo', 'Apr': 'Aprile',
    'May': 'Maggio', 'Jun': 'Giugno', 'Jul': 'Luglio', 'Aug': 'Agosto',
    'Sep': 'Settembre', 'Oct': 'Ottobre', 'Nov': 'Novembre', 'Dec': 'Dicembre'
}

# Function to search for a series/movie and check if the date matches
async def search(query, date, client, season, ismovie):
    response = await client.get(query)
    response = response.json()
    for json in response:
        link = json['link']
        tid = json['id']
        series_response = await client.get(link, headers=headers, allow_redirects=True, timeout=30)
        series_soup = BeautifulSoup(series_response.text, 'lxml')
        release_span = series_soup.find('span', class_='released')
        release_date = None
        if release_span:
            if release_span.text != "Data di uscita: N/A":
                date_string = release_span.text.split(': ')[-1]
                for eng, ita in month_mapping.items():
                    date_string = re.sub(rf'\b{eng}\b', ita, date_string)
                release_date = dateparser.parse(date_string, languages=['it']).strftime("%Y-%m-%d")
        if release_date == date:
            if ismovie == 0:
                # Search for the season
                Seasons = series_soup.find_all('span', class_="season-name")
                for i, item in enumerate(Seasons):
                    season_text = item.text.strip()
                    if season in season_text and "SUB" not in season_text:
                        return link, tid, i
            else:
                return link, tid, None
    return None, None, None

# Get episode link for series
def get_episode_link(actual_season, episode, tid, url):
    return f'{url}?show_video=true&post_id={tid}&season_id={actual_season}&episode_id={episode-1}'

# Get film link
def get_film(url):
    return url + "?show_video=true"

# Fetch real streaming link
async def get_real_link(tlink, client):
    page = await client.get(tlink, headers=headers, allow_redirects=True)
    soup = BeautifulSoup(page.content, 'lxml', parse_only=SoupStrainer('iframe'))
    iframe_src = soup.find('iframe')['src']
    iframe_page = await client.get(iframe_src, headers=headers, allow_redirects=True, timeout=30)
    iframe_soup = BeautifulSoup(iframe_page.content, 'lxml')
    mega_button = iframe_soup.find('div', attrs={'class': 'megaButton', 'rel': 'nofollow'}, string='MIXDROP')
    if mega_button:
        return mega_button.get('meta-link')
    return None

# Fetch the final streaming link
async def get_true_link(real_link, client):
    response = await client.get(real_link, headers=headers, allow_redirects=True, timeout=30)
    [s1, s2] = re.search(r"\}\('(.+)',.+,'(.+)'\.split", response.text).group(1, 2)
    schema = s1.split(";")[2][5:-1]
    terms = s2.split("|")
    charset = string.digits + string.ascii_letters
    d = dict(zip(charset, terms))
    s = 'https:'
    for c in schema:
        s += d.get(c, c)
    return s

# Main function to get the streaming link for a movie or series
async def filmpertutti(imdb, client):
    general = is_movie(imdb)
    ismovie = general[0]
    imdb_id = general[1]
    type = "Filmpertutti"
    season = general[2] if ismovie == 0 else None
    episode = int(general[3]) if ismovie == 0 else None

    if "tt" in imdb:
        showname, date = await get_info_imdb(imdb_id, ismovie, type, client)
    elif "tmdb" in imdb:
        tmdba = imdb_id.replace("tmdb:", "")
        showname, date = get_info_tmdb(tmdba, ismovie, type)
    
    showname = urllib.parse.quote_plus(showname.replace(" ", "+").replace("–", "+").replace("—", "+"))
    query = f'https://filmpertutti.{FT_DOMAIN}/wp-json/wp/v2/posts?search={showname}&page=1&_fields=link,id'
    
    try:
        url, tid, actual_season = await search(query, date, client, season, ismovie)
        if not url:
            print("MammaMia: No results found for Filmpertutti")
            return None
    except Exception as e:
        print(f"MammaMia: Error searching for Filmpertutti: {e}")
        return None

    # If it's a series
    if ismovie == 0:
        episode_link = get_episode_link(actual_season, episode, tid, url)
        real_link = await get_real_link(episode_link, client)
    else:
        film_link = get_film(url)
        real_link = await get_real_link(film_link, client)
    
    if real_link:
        streaming_link = await get_true_link(real_link, client)
        print(streaming_link)
        return streaming_link
    else:
        print("MammaMia: No streaming link found")
        return None
