import requests

def download_pdf(url):

    filename = url.split("/")[-1]

    response = requests.get(url)

    with open(filename, "wb") as f:
        f.write(response.content)

    return filename