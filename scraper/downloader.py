import requests

def download_pdf(url):

    filename = url.split("/")[-1]

    response = requests.get(url, timeout=30)

    response.raise_for_status()

    with open(filename, "wb") as f:
        f.write(response.content)

    return filename