import base64
with open("www.youtube.com_cookies.txt", "rb") as f:
    print(base64.b64encode(f.read()).decode())
