ARG BUILD_FROM
FROM $BUILD_FROM

RUN apk add --no-cache python3 py3-pip py3-aiohttp

WORKDIR /app
COPY app/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY app/ .

CMD ["python3", "main.py"]
