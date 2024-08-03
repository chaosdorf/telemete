FROM python:3.10-alpine
RUN pip install --no-cache-dir pipenv
RUN apk add --no-cache gcc musl-dev libffi-dev openssl-dev git

WORKDIR /usr/src/app

COPY Pipfile .
COPY Pipfile.lock .
RUN pipenv install --system --deploy
RUN mkdir data

COPY run.py . 
COPY .git .git
COPY templates templates

ENTRYPOINT [ "python", "/usr/src/app/run.py" ]
