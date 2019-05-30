from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, InlineQueryHandler, CallbackQueryHandler
from telegram import InlineQueryResultArticle, InputTextMessageContent, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, ParseMode
from raven import Client as RavenClient
from math import sqrt
import requests
import json
import sqlite3
import toml
from dealer.git import git
from os import environ
from pathlib import Path

# please see the README for configuration options


def get_secret(name):
    p = Path(f"/run/secrets/TELEMETE_{name}")
    if p.exists():
        return p.read_text().strip()
    print(f"WARN: Secret TELEMETE_{name} not found, falling back to environment variable {name}...")
    return environ[name]


API_KEY = get_secret('API_KEY')
try:
    SENTRY_DSN = get_secret('SENTRY_DSN')
except KeyError:
    SENTRY_DSN = None
    print("SENTRY_DSN not configured, not logging exceptions.")

config = toml.load(environ["CONFIG_FILE"])
BASE_URL = config['mete_connection']['base_url']
updater = Updater(token=API_KEY)
dispatcher = updater.dispatcher
raven_client = RavenClient(SENTRY_DSN) if SENTRY_DSN else None
database = sqlite3.connect("data/user_links")
cursor = database.cursor()

# This table contains the link between telegram and mete ids, whether or not a user is admin and their @-handle for telegram
cursor.execute('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, telegram_id INTEGER, mete_id INTEGER, admin INTEGER DEFAULT 0, user_handle TEXT)''')

# Check if initial admin has been linked and perform link if not
initial_admin = config['initial_admin']
cursor.execute('''SELECT id FROM users WHERE telegram_id=?''', (initial_admin['telegram_id'],))
if cursor.fetchone() is None:
    cursor.execute('''INSERT INTO users(telegram_id, mete_id, admin, user_handle) VALUES(?,?,?,?)''', (initial_admin['telegram_id'], initial_admin['mete_id'], 1, initial_admin['telegram_handle'],))
database.commit()
cursor.close()
del initial_admin

# Buttonlayout for non-registered users
kb_newusers = [[KeyboardButton("/start"), KeyboardButton("/list")]]

kb_newusers_markup = ReplyKeyboardMarkup(kb_newusers, resize_keyboard=True)


def record_exception(old_func):
    def new_func(bot, update):
        try:
            old_func(bot, update)
        except:  # noqa
            ident = None
            try:
                ident = raven_client.get_ident(raven_client.captureException())
            finally:
                output = "Sorry, the bot crashed."
                if ident:
                    output += f"\nThis issue has been logged with the id {ident}."
                bot.sendMessage(chat_id=update.message.chat_id, text=output)
    return new_func


@record_exception
def commandStart(bot, update): # Startup and help message
    mete_id = getMeteID(update.message.chat_id)
    bot_name = bot.first_name
    if not bot.last_name is None:
        bot_name += bot.last_name
    output = "*Welcome to the {} UI!*\n".format(bot_name)
    if mete_id is None:
        output += "You are currently not linked with a mete account. Please contact one of the administrators:\n"
        database = sqlite3.connect("data/user_links")
        cursor = database.cursor()
        cursor.execute('''SELECT user_handle FROM users WHERE admin=1''')
        admin_handles = cursor.fetchall()
        cursor.close()
        for u in admin_handles:
            output += "@{}\n".format(u[0])
        output += "Please have your mete ID ready to speed up the process."
        bot.sendMessage(chat_id=update.message.chat_id, text=output, reply_markup=kb_newusers_markup, parse_mode=ParseMode.MARKDOWN)
    else:
        output += "\nJust press one of the buttons below to buy a drink!\n\n"
        output += "/balance shows your account balance.\n\n"
        output += "/help displays this message."

        database = sqlite3.connect("data/user_links")
        cursor = database.cursor()
        cursor.execute('''SELECT admin FROM users WHERE mete_id=?''', (mete_id, ))
        admin = cursor.fetchone()[0]
        cursor.close()

        if admin:
            output += "\n\n*Admin only:*\n\n"
            output += "You can link users via inline-mode.\n"
            output += "Open the user's chat. Then type _@{} link mete-id_ where mete-id is the other user's mete ID you wish to link.\n".format(bot.username)
            output += "Click on 'Send link request'. The other user then presses the button 'Link accounts'.\n\n"
            output += "User promotion works the same way. Type _@{} promote_ and click on 'Send promotion request'. The other user then presses the button 'Become administrator'.".format(bot.username)

        output += f"\n\nThis bot is running telemete [{git.revision}](https://github.com/chaosdorf/telemete/tree/{git.revision})."
        bot.sendMessage(chat_id=update.message.chat_id, text=output, reply_markup=getDefaultKeyboardMarkup(), parse_mode=ParseMode.MARKDOWN)


@record_exception
def commandBalance(bot, update): # Display current balance of user
    mete_id = getMeteID(update.message.chat_id)
    if mete_id is None:
        output = "You are not linked to a mete account!"
        bot.sendMessage(chat_id=update.message.chat_id, text=output, reply_markup=kb_newusers_markup)
    else:
        balance = getBalance(mete_id)
        output = "Your balance is _{:.2f}€_".format(balance)
        if balance < 0: # Alert for negative account balance
            output += "\n\n*Your account balance is negative.*"
        bot.sendMessage(chat_id=update.message.chat_id, text=output, reply_markup=getDefaultKeyboardMarkup(), parse_mode=ParseMode.MARKDOWN)


@record_exception
def commandCancel(bot, update): # Cancel action and return to standard button layout
    mete_id = getMeteID(update.message.chat_id)
    if mete_id is None:
        output = "You are not linked to a mete account!"
        bot.sendMessage(chat_id=update.message.chat_id, text=output, reply_markup=kb_newusers_markup)
    else:
        output = "This request has been cancelled."
        bot.sendMessage(chat_id=update.message.chat_id, text=output, reply_markup=getDefaultKeyboardMarkup())


@record_exception
def handle_inlinerequest(bot, update): # Handle any inline requests to this bot
    query = update.inline_query
    sender_id = query.from_user.id
    database = sqlite3.connect("data/user_links")
    cursor = database.cursor()


    # Inline requests can only be started by admins, check this
    cursor.execute('''SELECT admin FROM users WHERE telegram_id=?''', (sender_id,))
    isAdmin = cursor.fetchone()

    if isAdmin is None:
        return

    isAdmin = isAdmin[0]

    if not isAdmin:
        return

    results = list()
    input = query.query.split(" ")
    if input[0] == "link": # Link the recipient of the message to the specified mete account (Needs to be confirmed by recipient)
        mete_id = int(input[1])
        # Get a list of all users (list[dict()])
        mete_user_list = json.loads(requests.get(f"{BASE_URL}/api/v1/users.json").text)

        valid_user = False
        for user in mete_user_list:
            if user['id'] == mete_id:
                mete_name = user['name']
                valid_user = True
                break
        if not valid_user:
            return

        cursor.execute('''SELECT id FROM users WHERE mete_id=?''', (mete_id,))
        if not (cursor.fetchone() is None):
            # The user is already linked - print a helpful error message
            output = "This Telegram account is already linked to the Mete account *{}*_(id: {})_. 😔".format(mete_name, mete_id)
            kb_link = [[InlineKeyboardButton("Sorry...", callback_data="cancel")]]
            kb_link_markup = InlineKeyboardMarkup(kb_link)

            results.append(InlineQueryResultArticle(id="0", title="User already linked!", input_message_content=InputTextMessageContent(output, parse_mode=ParseMode.MARKDOWN), reply_markup=kb_link_markup))
        else:
            # User is not linked yet - send link request buttons
            output = "Press 'Link accounts' to link your Telegram account to the Mete account *{}*_(id: {})_.".format(mete_name, mete_id)
            kb_link = [[InlineKeyboardButton("Link accounts", callback_data="link/" + str(mete_id))], [InlineKeyboardButton("Cancel", callback_data="cancel")]]
            kb_link_markup = InlineKeyboardMarkup(kb_link)

            results.append(InlineQueryResultArticle(id="0", title="Send link request", input_message_content=InputTextMessageContent(output, parse_mode=ParseMode.MARKDOWN), reply_markup=kb_link_markup))
    elif input[0] == "promote": # Promote the recipient of the message to be an administrator (Needs to be confirmed by recipient)
        output = "Press 'Become administrator' to become a Chaosdorf-Mete administrator."
        kb_admin_requests = [[InlineKeyboardButton("Become administrator", callback_data="promote")], [InlineKeyboardButton("Cancel", callback_data="cancel")]]
        kb_admin_requests_markup = InlineKeyboardMarkup(kb_admin_requests)

        results.append(InlineQueryResultArticle(id="0", title="Send promotion request", input_message_content=InputTextMessageContent(output), reply_markup=kb_admin_requests_markup))
    bot.answer_inline_query(query.id, results)
    cursor.close()


@record_exception
def handle_buttonpress(bot, update): # Handle any inline buttonpresses related to this bot
    query = update.callback_query
    data = query.data.split("/")
    if data[0] == "link": # Confirm the linking of Telegram and Mete accounts
        mete_id = int(data[1])
        telegram_id = query.from_user.id

        database = sqlite3.connect("data/user_links")
        cursor = database.cursor()
        cursor.execute('''SELECT id FROM users WHERE telegram_id=?''', (telegram_id,))
        if not (cursor.fetchone() is None):
            output = "*ERROR*: This user is already linked to Mete!"
            answer = "Error!"
        else:
            cursor.execute('''INSERT INTO users(telegram_id, mete_id, user_handle) VALUES(?,?,?)''', (telegram_id, mete_id,"?",))
            output = "Successfully connected this user to Mete!"
            answer = "Success!"
        database.commit()
        cursor.close()
    elif data[0] == "promote": # Confirm the promotion of users
        a = 0
        abort = False
        user = query.from_user
        telegram_id = user.id
        mete_id = getMeteID(telegram_id)
        if mete_id is None:
            output = "*ERROR*: This user is not linked to Mete!"
            answer = "Error!"
        else:
            database = sqlite3.connect("data/user_links")
            cursor = database.cursor()

            cursor.execute('''SELECT admin FROM users WHERE telegram_id=?''', (telegram_id,))
            isAdmin = cursor.fetchone()[0]
            if isAdmin:
                output = "*ERROR*: This user is already an administrator!"
                answer = "Error!"
            else:
                if user.username is None:
                    output = "*ERROR*: This user does not have a username!"
                    answer = "Error!"
                else:
                    user_handle = user.username
                    cursor.execute('''UPDATE users SET admin=1 WHERE telegram_id=?''', (telegram_id,))
                    cursor.execute('''UPDATE users SET user_handle=? WHERE telegram_id=?''', (user_handle, telegram_id,))
                    database.commit()

                    output = "Successfully promoted this user to administrator!"
                    output = "Success!"
            cursor.close()
    elif data[0] == "cancel": # Cancel inline requests
        output = "This request has been cancelled."
        answer = "Cancelled!"
    bot.edit_message_text(output, inline_message_id=query.inline_message_id, parse_mode=ParseMode.MARKDOWN)
    bot.answer_callback_query(query.id, text=answer)


@record_exception
def handle_textinput(bot, update): # Handle any non-command text input to this bot
    mete_id = getMeteID(update.message.chat_id)
    if mete_id is None:
        output = "You are not linked to a mete account!"
        bot.sendMessage(chat_id=update.message.chat_id, text=output, reply_markup=kb_newusers_markup, parse_mode=ParseMode.MARKDOWN)
        return
    input = update.message.text
    splitup_input = input.split(":")
    if len(splitup_input) == 2: # Check whether the input specifies a valid drink and purchase the drink
        # input looks like this: 'name: x.xx€'. name can be carried over, for price the space and the € need to be removed, hence the slicing [1:-1] (everything but first and last char)
        name, price = splitup_input[0], splitup_input[1][1:-1]
        abort = True

        # Get a list of all drinks (list[dict()])
        drink_list = json.loads(requests.get(f"{BASE_URL}/api/v1/drinks.json").text)

        for drink in drink_list:
            if name == drink['name'] and price == "{:.2f}".format(float(drink['price'])):
                drink_id = drink['id']
                abort = False
                break
        if not abort:
            # Buy a drink via http request
            requests.get("{}/api/v1/users/{}/buy?drink={}".format(BASE_URL, mete_id, drink_id))
            balance = getBalance(mete_id)
            output = "You purchased _{}_. Your new balance is _{:.2f}€_".format(name, balance)
            if balance < 0: # Alert for negative account balance
                output += "\n\n*Your account balance is negative.*"
            bot.sendMessage(chat_id=update.message.chat_id, text=output, reply_markup=getDefaultKeyboardMarkup(), parse_mode=ParseMode.MARKDOWN)
            return
    output = "Your input confused me. Get some /help"
    bot.sendMessage(chat_id=update.message.chat_id, text=output, reply_markup=getDefaultKeyboardMarkup(), parse_mode=ParseMode.MARKDOWN)

def getMeteID(telegram_id): # Returns the mete id linked to the specified telegram id or None, if there is no link
    database = sqlite3.connect("data/user_links")
    cursor = database.cursor()

    cursor.execute('''SELECT mete_id FROM users WHERE telegram_id=?''', (telegram_id,))
    mete_id = cursor.fetchone()
    cursor.close()
    if mete_id is None:
        return None
    else:
        return mete_id[0]

def getBalance(mete_id): # Returns the specified user's balance as a float (Only used by other functions, validity of the mete id needs to be checked prior to calling this!)
    # Get a list of all users (list[dict()])
    mete_user_list = json.loads(requests.get(f"{BASE_URL}/api/v1/users.json").text)
    for user in mete_user_list:
        if user['id'] == mete_id:
            balance = float(user['balance'])
            break
    return balance

def getDefaultKeyboardMarkup(): # Returns a keyboard containing buttons for every drink marked as active
    drink_list = json.loads(requests.get(f"{BASE_URL}/api/v1/drinks.json").text)
    kb_default = list()

    # Only list active drinks
    active_drinks = []
    for drink in drink_list:
        if drink["active"]:
            active_drinks.append(drink)
    n = int(len(active_drinks)/3) + 1
    for i in range(n+1):
        column_drinks = list()
        for drink in active_drinks[i*3:(i+1)*3]:
            drink_details = "{}: {:.2f}€".format(drink['name'], float(drink['price']))
            column_drinks.append(KeyboardButton(drink_details))
        kb_default.append(column_drinks)
    kb_default.append([KeyboardButton("/balance"), KeyboardButton("/help")])
    kb_default_markup = ReplyKeyboardMarkup(kb_default)
    return kb_default_markup

dispatcher.add_handler(CommandHandler('start', commandStart))
dispatcher.add_handler(CommandHandler('help', commandStart))
dispatcher.add_handler(CommandHandler('balance', commandBalance))
dispatcher.add_handler(CommandHandler('cancel', commandCancel))
dispatcher.add_handler(InlineQueryHandler(handle_inlinerequest))
dispatcher.add_handler(CallbackQueryHandler(handle_buttonpress))
dispatcher.add_handler(MessageHandler(Filters.text, handle_textinput))

updater.start_polling()

updater.idle()

database.close()
