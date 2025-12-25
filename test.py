import requests


def send(input_number):
    s = requests.Session()  # this is a requests library to make a http connection
    try:
        headers = {'Content-Type': 'application/json'}
        payloads = {
            'url': 'hhhhhhhhh',
            'ip': f'{input_number}',
            'useragent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
        }
        req = s.post('http://104.194.157.122:8000/tracker/api/log/', headers=headers, json=payloads)
        print(req.text)
    except Exception as e:
        print(e)
        # you can print error as e here the errors was come form bad connection or losing internet or proxy >> etc
        return 2


send('8.8.8.8')
