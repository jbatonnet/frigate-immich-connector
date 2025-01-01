# docker build -t ghcr.io/jbatonnet/frigate-immich-connector .
# docker run --rm -it -v .\.env:/usr/src/app/.env ghcr.io/jbatonnet/frigate-immich-connector

FROM python:3

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py ./

CMD [ "python", "./main.py" ]
