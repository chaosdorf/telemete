from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, InlineQueryHandler, CallbackQueryHandler
from telegram import InlineQueryResultArticle, InputTextMessageContent, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, ParseMode
import sentry_sdk
from jinja2 import Environment, FileSystemLoader
from math import sqrt
import requests
import json
import sqlite3
import toml
from dealer.git import git
from os import environ
from pathlib import Path
from traceback import print_exc

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
jinja_env = Environment(loader=FileSystemLoader("templates"))
updater = Updater(token=API_KEY, use_context=True)
dispatcher = updater.dispatcher
if SENTRY_DSN:
    sentry_sdk.init(SENTRY_DSN)
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
    def new_func(update, context):
        try:
            old_func(update, context)
        except Exception as e:  # noqa
            ident = None
            output = "Sorry, the bot crashed."
            print_exc()
            try:
                if SENTRY_DSN:
                    sentry_sdk.capture_exception(e)
                    output += "\nThis issue has been logged."
            finally:
                context.bot.sendMessage(chat_id=update.message.chat_id, text=output)
    return new_func


@record_exception
def commandStart(update, context): # Startup and help message
    mete_id = getMeteID(update.message.chat_id)
    bot_name = context.bot.first_name
    if not context.bot.last_name is None:
        bot_name += context.bot.last_name
    
    database = sqlite3.connect("data/user_links")
    cursor = database.cursor()
    if mete_id is None:
        cursor.execute('''SELECT user_handle FROM users WHERE admin=1''')
        admin_handles = cursor.fetchall()
        admin = None
        reply_markup = kb_newusers_markup
    else:
        cursor.execute('''SELECT admin FROM users WHERE mete_id=?''', (mete_id, ))
        admin = cursor.fetchone()[0]
        admin_handles = None
        reply_markup = getDefaultKeyboardMarkup()
    cursor.close()
    
    output = jinja_env.get_template("start.j2").render(
        bot_name=bot_name,
        bot_nick=context.bot.username,
        git_revision=git.revision,
        admin_handles=admin_handles,
        mete_id=mete_id,
        admin=admin,
    )
    context.bot.sendMessage(
        chat_id=update.message.chat_id,
        text=output,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN,
    )


@record_exception
def commandBalance(update, context): # Display current balance of user
    mete_id = getMeteID(update.message.chat_id)
    if mete_id is None:
        output = "You are not linked to a mete account!"
        context.bot.sendMessage(chat_id=update.message.chat_id, text=output, reply_markup=kb_newusers_markup)
    else:
        balance = getBalance(mete_id)
        output = jinja_env.get_template("balance.j2").render(balance=balance)
        context.bot.sendMessage(chat_id=update.message.chat_id, text=output, reply_markup=getDefaultKeyboardMarkup(), parse_mode=ParseMode.MARKDOWN)


@record_exception
def commandCancel(update, context): # Cancel action and return to standard button layout
    mete_id = getMeteID(update.message.chat_id)
    if mete_id is None:
        output = "You are not linked to a mete account!"
        context.bot.sendMessage(chat_id=update.message.chat_id, text=output, reply_markup=kb_newusers_markup)
    else:
        output = "This request has been cancelled."
        context.bot.sendMessage(chat_id=update.message.chat_id, text=output, reply_markup=getDefaultKeyboardMarkup())


@record_exception
def handle_inlinerequest(update, context): # Handle any inline requests to this bot
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

    results = list()
    input = query.query.split(" ")
    if input[0] == "link" and isAdmin and len(input) >= 2: # Link the recipient of the message to the specified mete account (Needs to be confirmed by recipient)
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
    elif input[0] == "promote" and isAdmin: # Promote the recipient of the message to be an administrator (Needs to be confirmed by recipient)
        output = "Press 'Become administrator' to become a Chaosdorf-Mete administrator."
        kb_admin_requests = [[InlineKeyboardButton("Become administrator", callback_data="promote")], [InlineKeyboardButton("Cancel", callback_data="cancel")]]
        kb_admin_requests_markup = InlineKeyboardMarkup(kb_admin_requests)

        results.append(InlineQueryResultArticle(id="0", title="Send promotion request", input_message_content=InputTextMessageContent(output), reply_markup=kb_admin_requests_markup))
    else:
        results.append(InlineQueryResultArticle(id="0", title="Send drink buttons", input_message_content=InputTextMessageContent("Please press one of the buttons below to buy a drink."), reply_markup=getDrinkInlineKeyboardMarkup()))
    context.bot.answer_inline_query(query.id, results, cache_time=0)
    cursor.close()


@record_exception
def handle_buttonpress(update, context): # Handle any inline buttonpresses related to this bot
    query = update.callback_query
    data = query.data.split("/")
    current_keyboard = None
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
    try:
        drink_id = int(data[0])
        user = query.from_user
        telegram_id = user.id
        mete_id = getMeteID(telegram_id)
        if mete_id is None:
            output = "*ERROR*: This user is not linked to Mete!"
            answer = "Error!"
        else:
            requests.get("{}/api/v1/users/{}/buy?drink={}".format(BASE_URL, mete_id, drink_id))

            drink_list = json.loads(requests.get(f"{BASE_URL}/api/v1/drinks.json").text)

            for drink in drink_list:
                if drink['id'] == drink_id:
                    drink_name = drink['name']
                    drink_price = float(drink['price'])
                    break

            if not user.username is None:
                username = user.username
            else:
                username = user.first_name
            
            output = "*{}* has bought _{}_ for _{:.2f}€_.".format(username, drink_name, drink_price)
            answer = "Bought a drink!"
        output += "\n\nPlease press one of the buttons below to buy a drink."
        current_keyboard = getDrinkInlineKeyboardMarkup()
    except ValueError:
        pass
    context.bot.edit_message_text(output, inline_message_id=query.inline_message_id, parse_mode=ParseMode.MARKDOWN, reply_markup=current_keyboard)
    context.bot.answer_callback_query(query.id, text=answer)


@record_exception
def handle_textinput(update, context): # Handle any non-command text input to this bot
    mete_id = getMeteID(update.message.chat_id)
    if mete_id is None:
        output = "You are not linked to a mete account!"
        context.bot.sendMessage(chat_id=update.message.chat_id, text=output, reply_markup=kb_newusers_markup, parse_mode=ParseMode.MARKDOWN)
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
            output = jinja_env.get_template("balance.j2").render(
                product=name,
                balance=balance,
            )
            context.bot.sendMessage(chat_id=update.message.chat_id, text=output, reply_markup=getDefaultKeyboardMarkup(), parse_mode=ParseMode.MARKDOWN)
            return
    output = "Your input confused me. Get some /help"
    context.bot.sendMessage(chat_id=update.message.chat_id, text=output, reply_markup=getDefaultKeyboardMarkup(), parse_mode=ParseMode.MARKDOWN)

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

def getDrinkInlineKeyboardMarkup(): # Returns a keyboard containing buttons for every drink marked as active for inline mode
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
            column_drinks.append(InlineKeyboardButton(drink['name'], callback_data=str(drink['id'])))
        kb_default.append(column_drinks)
    kb_default_markup = InlineKeyboardMarkup(kb_default)
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
