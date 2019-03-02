FROM python:3.7-alpine
RUN pip install --no-cache-dir pipenv
RUN apk add --no-cache gcc musl-dev libffi-dev openssl-dev

WORKDIR /usr/src/app

COPY Pipfile .
COPY Pipfile.lock .
RUN pipenv install --system --deploy
RUN mkdir data

COPY run.py . 

ENTRYPOINT [ "python", "/usr/src/app/run.py" ]
