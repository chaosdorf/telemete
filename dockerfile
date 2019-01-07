FROM python:3.7.2

WORKDIR /usr/src/app

RUN pip install python-telegram-bot
RUN pip install requests

COPY . .

ENTRYPOINT [ "python", "/usr/src/app/run.py" ]

