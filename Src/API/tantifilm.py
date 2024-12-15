from bs4 import BeautifulSoup, SoupStrainer
import re
import time
import urllib.parse
from Src.Utilities.info import is_movie, get_info_imdb, get_info_tmdb
import Src.Utilities.config as config
from Src.Utilities.loadenv import load_env
HF = config.HF
env_vars = load_env()
PROXY_CREDENTIALS = env_vars.get('PROXY_CREDENTIALS')
ForwardProxy_list = config.ForwardProxy
ForwardProxy = ForwardProxy_list[0]
TF_DOMAIN = config.TF_DOMAIN

async def search(showname, ismovie, date, client):
    showname = urllib.parse.quote_plus(showname.replace(" ", "%20"))
    url = f'https://www.tanti.bond/ajax/posts?q={showname}'
    response = await client.post(url, allow_redirects=True, impersonate="chrome120")
    response_data = (await response.json())['data']
    
    if not response_data:  # Check if response data is empty or None
        return None  # Return None if no results found
    
    if ismovie == 1:
        for link in response_data:
            url = link['url']
            response = await client.get(url, allow_redirects=True, impersonate="chrome120")
            pattern = r'Data di rilascio\s*</div>\s*<div class="text">\s*(\d{4})\s*</div>'
            found_date = re.search(pattern, await response.text())
            release_date = str(found_date.group(1))
            if release_date == date:
                tid = url.split('-')[-1]
                return tid, url
    elif ismovie == 0: 
        for link in response_data:
            base_url = link['url']
            url = f'{base_url}-1-season-1-episode'
            response = await client.get(url, allow_redirects=True, impersonate="chrome120")
            pattern = r'Data di rilascio\s*</div>\s*<div class="text">\s*(\d{4})\s*</div>'
            found_date = re.search(pattern, await response.text())
            release_date = str(found_date.group(1))
            if release_date == date:
                tid = url.split('-')[1]
                soup = BeautifulSoup(await response.text(), 'lxml')
                a_tag = soup.find('a', class_='dropdown-toggle btn-service selected')
                embed_id = a_tag['data-embed']
                return url, embed_id

async def fast_search(showname, ismovie, client):
    showname = urllib.parse.quote_plus(showname.replace(" ", "%20"))
    url = f'https://www.tanti.{TF_DOMAIN}/search/{showname}'
    response = await client.get(url, allow_redirects=True, impersonate="chrome120")
    soup = BeautifulSoup(await response.text(), "lxml")
    
    if ismovie == 1:
        first_link = soup.select_one('#movies .col .list-media')
        if not first_link:
            return None  # Check if the first link is None
        url = first_link['href']
        tid = url.split('-')[1]
        return tid, url
    elif ismovie == 0: 
        first_link = soup.select_one('#series .col .list-media')
        if not first_link:
            return None  # Check if the first link is None
        base_url = first_link['href']
        url = f'{base_url}-1-season-1-episode'
        response = await client.get(url, allow_redirects=True, impersonate="chrome120")
        soup = BeautifulSoup(await response.text(), 'lxml')
        a_tag = soup.find('a', class_='dropdown-toggle btn-service selected')
        if not a_tag:
            return None  # Check if the a_tag is None
        embed_id = a_tag['data-embed']
        return url, embed_id

async def get_protect_link(id, url, client):
    response = await client.get(f"https://p.hdplayer.casa/myadmin/play.php?id={id}", allow_redirects=True, impersonate="chrome120")
    soup = BeautifulSoup(await response.text(), "lxml", parse_only=SoupStrainer('iframe'))
    protect_link = soup.iframe['src']
    
    if "protect" in protect_link:
        return protect_link
    else:
        response = await client.get(url, allow_redirects=True, impersonate="chrome120")
        soup = BeautifulSoup(await response.text(), 'lxml')
        embed_id = soup.find('a', class_='dropdown-toggle btn-service selected')['data-embed']
        headers = {'User-Agent': 'Mozilla/5.0', 'Referer': url}
        data = {'id': embed_id}
        ajax_url = f"https://www.tanti.{TF_DOMAIN}/ajax/embed"
        response = await client.post(ajax_url, headers=headers, data=data)
        hdplayer = response.text[43:-27]
        response = await client.get(hdplayer, allow_redirects=True, impersonate="chrome120")
        soup = BeautifulSoup(await response.text(), 'lxml')
        
        links_dict = {}
        li_tags = soup.select('ul.nav.navbar-nav li.dropdown')
        for li_tag in li_tags:
            a_tag = li_tag.find('a')
            if a_tag:
                title = a_tag.text.strip()
                if title != "1" and "Tantifilm" not in title:
                    href = a_tag['href']
                    response = await client.get(href, allow_redirects=True, impersonate="chrome120")
                    soup = BeautifulSoup(await response.text(), "lxml", parse_only=SoupStrainer('iframe'))
                    protect_link = soup.iframe['src']
                    if "protect" in protect_link:
                        links_dict[title] = protect_link
        if not links_dict:
            return None  # Return None if links_dict is empty
        return links_dict

async def true_url(protect_link, client):
    headers = {"Range": "bytes=0-", "Referer": "https://d000d.com/"}
    
    if HF == "1":
        import random
        import json
        proxy_list = json.loads(PROXY_CREDENTIALS)
        proxy = random.choice(proxy_list) if proxy_list else ""
        proxies = {"http": proxy, "https": proxy} if proxy else {}
        
        response = await client.head(protect_link, allow_redirects=True, impersonate="chrome120", proxies=proxies)
        doodstream_url = response.url
    else:
        proxies = {}
        doodstream_url = protect_link
    
    response = await client.get(ForwardProxy + doodstream_url, allow_redirects=True, impersonate="chrome120", proxies=proxies)
    
    if response.status_code == 200:
        real_time = str(int(time.time()))
        pattern = r"(\/pass_md5\/.*?)'.*(\?token=.*?expiry=)"
        match = re.search(pattern, await response.text(), re.DOTALL)
        
        if match:
            url = f'https://d000d.com{match[1]}'
            rebobo = await client.get(ForwardProxy + url, headers=headers, allow_redirects=True, impersonate="chrome120", proxies=proxies)
            real_url = f'{await rebobo.text()}123456789{match[2]}{real_time}'
            print("MammaMia: Found results for Tantifilm")
            return real_url
        else:
            print("No match found in the text.")
            return None
    print("Error: Could not get the response.")
    return None

async def tantifilm(imdb, client, TF_FAST_SEARCH):
    urls = None
    try:
        general = is_movie(imdb)
        ismovie = general[0]
        imdb_id = general[1]
        if ismovie == 0 : 
            season = int(general[2])
            episode = int(general[3])
            if "tt" in imdb:
                if TF_FAST_SEARCH == "0":
                    type = "Tantifilm"
                    showname, date = await get_info_imdb(imdb_id, ismovie, type, client)
                    url, embed_id = await search(showname, ismovie, date, client)
                elif TF_FAST_SEARCH == "1":
                    type = "TantifilmFS"
                    showname = await get_info_imdb(imdb_id, ismovie, type, client)
                    url, embed_id = await fast_search(showname, ismovie, client)
            else:
                tmdba = imdb_id.replace("tmdb:", "")
                if TF_FAST_SEARCH == "0":
                    type = "Tantifilm"
                    showname, date = get_info_tmdb(tmdba, ismovie, type)
                    url, embed_id = await search(showname, ismovie, date, client)
                elif TF_FAST_SEARCH == "1":
                    type = "TantifilmFS"
                    showname = get_info_tmdb(tmdba, ismovie, type)
                    url, embed_id = await fast_search(showname, ismovie, client)
            if not url:
                return None  # Check if the url is None
            protect_link = await get_protect_link(tid, url, client)
            if protect_link is None:
                return None  # Check if protect_link is None
            url = await true_url(protect_link, client)
            if url:
                return url
        elif ismovie == 1:
            if "tt" in imdb:
                if TF_FAST_SEARCH == "0":
                    type = "Tantifilm"
                    showname, date = await get_info_imdb(imdb_id, ismovie, type, client)
                    tid, url = await search(showname, ismovie, date, client)
                elif TF_FAST_SEARCH == "1":
                    type = "TantifilmFS"
                    showname = await get_info_imdb(imdb_id, ismovie, type, client)
                    date = None
                    tid, url = await fast_search(showname, ismovie, client)
            else:
                if TF_FAST_SEARCH == "0":
                    type = "Tantifilm"
                    showname, date = get_info_tmdb(imdb, ismovie, type)
                    tid, url = await search(showname, ismovie, date, client)
                elif TF_FAST_SEARCH == "1":
                    type = "TantifilmFS"
                    showname = get_info_tmdb(imdb, ismovie, type)
                    tid, url = await fast_search(showname, ismovie, client)
            protect_link = await get_protect_link(tid, url, client)
            if not isinstance(protect_link, str):
                urls = protect_link
                if urls:
                    return urls
                else:
                    print("Tantifilm Error v2")
            else:
                url = await true_url(protect_link, client)
                if url:
                    return url
    except Exception as e:
        print("Tantifilm Error: ", e)
        return None
