FROM python:3.7-alpine
RUN apk add --no-cache gcc musl-dev libffi-dev openssl-dev

WORKDIR /usr/src/app

RUN pip install python-telegram-bot
RUN pip install requests
RUN mkdir data

COPY run.py . 

ENTRYPOINT [ "python", "/usr/src/app/run.py" ]
