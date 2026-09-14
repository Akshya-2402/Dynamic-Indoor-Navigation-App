import requests
url='http://127.0.0.1:5000/map_match'
resp = requests.post(url, json={'floor':'Level_1','x':0,'y':0})
print('status', resp.status_code)
print(resp.text)
