# telemete

access your [Mete](https://github.com/chaosdorf/mete) account with a Telegram bot

## development

Simply clone this repository, run `pipenv install --dev` and you're good to go.

## deployment

You can use [the prebuilt Docker image](https://hub.docker.com/r/ytvwld/telemete) or build it yourself.

## configuration

You'll need a config file. It looks like this:

```toml
[mete_connection]
base_url = "http://mete/" # the URL of your Mete instance - please use HTTPS

[initial_admin] # information about the initial administrator
telegram_id = 1234 # can be obtained from t.me/userinfobot or @userinfobot on Telegram
telegram_handle = "foo"
mete_id = 5678
```

Please put the path to this config file in the environment variable `CONFIG_FILE`.

Additionally, there are two secret keys you can configure:

 * `API_KEY` (required): the key from Telegram's botfather
 * `SENTRY_DSN` (recommended): the key for the project in Sentry


Both can be given either using [Docker's mechanism for secrets](https://docs.docker.com/engine/reference/commandline/secret/) (prefix them with `TELEMETE_`) or as environment variables.

Sidenote: This bot requires all administrators to have a user handle on telegram for the purpose of users easily contacting them.
So make sure only users with handles get promoted.
