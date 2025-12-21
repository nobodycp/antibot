import requests


def send(input_number):
    s = requests.Session()  # this is a requests library to make a http connection
    try:
        # :
        # :
        # :
        # :
        # :
        # Content-Length: 107
        # :
        # Connection: keep-alive
        # Cookie:
        # Priority: u=0
        # Pragma: no-cache
        # Cache-Control: no-cache
        headers = {
            'Accept': '*/*',
            'Referer': 'http://104.194.157.122:8000/tracker/blocked-isp/',
            'HX-Request': 'true',
            'HX-Target': 'blocked-subnets-wrapper',
            'HX-Current-URL': 'http://104.194.157.122:8000/tracker/blocked-subnets/',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'http://104.194.157.122:8000',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Cookie': 'csrftoken=0mhOgDis5K2dLEIyijejeepVhvd3iDil; sessionid=q182u7eyqrbql04u3wlnef2wevig856m',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:146.0) Gecko/20100101 Firefox/146.0',
        }
        payloads = {
            'csrfmiddlewaretoken': '58yPkNC9IgxBjWP2HMu4vbeHCNBd7cfYVkFtqgKrDQpEUqnqPVydzftsJ8E6fFn9',
            'isp_name': f'{input_number}',
        }
        req = s.post('http://104.194.157.122:8000/tracker/blocked-isp/', headers=headers, data=payloads)
        # print(req.text)
        print(f"{input_number} ----> was added")
    except Exception as e:
        print(e)
        # you can print error as e here the errors was come form bad connection or losing internet or proxy >> etc
        return 2


# send('5.29.87.1/32')
with open('isp.txt') as file:
    for line in file:
        send(str(line).strip())