import requests


def send(input_number):
    s = requests.Session()  # this is a requests library to make a http connection
    try:
        headers = {'Content-Type': 'application/json'}
        payloads = {
            'ip': f'{input_number}',
            'useragent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
            # 'url': 'hhhhhhhhh',
        }
        req = s.post('http://0.0.0.0:8001/tracker/api/log/', headers=headers, json=payloads)
        print(req.text)
    except Exception as e:
        print(e)
        # you can print error as e here the errors was come form bad connection or losing internet or proxy >> etc
        return 2


send('5.28.189.173')
