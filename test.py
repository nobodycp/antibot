import requests



def save_browser_checker(i):
    headers = {
        'Host': 'transparencyreport.google.com',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:139.0) Gecko/20100101 Firefox/139.0',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Alt-Used': 'transparencyreport.google.com',
    }
    req = requests.get(f'https://transparencyreport.google.com/transparencyreport/api/v3/safebrowsing/status?site={i}', headers=headers)
    # print(req.text)
    if 'true' in req.text:
        print("Red Flag")
    else:
        print("Working")

def redirect_checker(link, keyword):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:139.0) Gecko/20100101 Firefox/139.0',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
    }
    req = requests.get(f"{link}", headers=headers, allow_redirects=False)
    # print(req.status_code)
    # print(req.headers.get("Location"))
    if req.status_code == 302:
        if f'{keyword}' in req.headers.get('Location'):
            return "working"
        else:
            return "not working"
    else:
        return "error"

# save_browser_checker('https://gthelema01.ivyro.net/')
redirect_checker('https://dashboard.testahel.sa/ini.php', 'Post/index.php')