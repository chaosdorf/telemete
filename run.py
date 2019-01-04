from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, InlineQueryHandler, CallbackQueryHandler
from telegram import InlineQueryResultArticle, InputTextMessageContent, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, ParseMode
from valuables import API_KEY, BASE_ADDRESS, INIT_ADMIN
from math import sqrt
import requests
import json
import sqlite3

updater = Updater(token=API_KEY)
dispatcher = updater.dispatcher
database = sqlite3.connect("user_data")
cursor = database.cursor()

cursor.execute('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, telegram_id INTEGER, mete_id INTEGER, admin INTEGER DEFAULT 0, user_handle TEXT)''')
cursor.execute('''SELECT id FROM users WHERE telegram_id=?''', (INIT_ADMIN['telegram_id'],))
if cursor.fetchone() is None:
    cursor.execute('''INSERT INTO users(telegram_id, mete_id, admin, user_handle) VALUES(?,?,?,?)''', (INIT_ADMIN['telegram_id'], INIT_ADMIN['mete_id'], 1, INIT_ADMIN['user_handle'],))
database.commit()
cursor.close()

kb = [[KeyboardButton("/list"), KeyboardButton("/buy"), KeyboardButton("/balance"), KeyboardButton("/help")]]
kb_helponly = [[KeyboardButton("/help")]]

kb_markup = ReplyKeyboardMarkup(kb, resize_keyboard=True)
kb_helponly_markup = ReplyKeyboardMarkup(kb_helponly, resize_keyboard=True)

def commandStart(bot, update): # Startup and help message
    mete_id = getMeteID(update.message.chat_id)
    output = "Welcome to the Chaosdorf-Mete UI!\n"
    if mete_id is None:
        output += "You are currently not linked with a mete account. Please contact one of the administrators:\n"
        database = sqlite3.connect("user_data")
        cursor = database.cursor()
        cursor.execute('''SELECT user_handle FROM users WHERE admin=1''')
        admin_handles = cursor.fetchall()
        for u in admin_handles:
            output += "@{}\n".format(u[0])
        output += "Please have your mete id at the ready to speed up the process."
        bot.sendMessage(chat_id=update.message.chat_id, text=output, reply_markup=kb_helponly_markup)
    else:
        output += "\n/list lists all available drinks and their prices.\n\n"
        output += "/balance shows your account balance.\n\n"
        output += "/buy displays buttons for each beverage to purchase said beverage.\n\n"
        output += "/help displays this message."
        bot.sendMessage(chat_id=update.message.chat_id, text=output, reply_markup=kb_markup)

def commandList(bot, update): # Display available drinks
    drink_list = json.loads(requests.get(f"http://{BASE_ADDRESS}/api/v1/drinks.json").text)

    output = "Available drinks:\n"

    for drink in drink_list:
        output += "\n{}: _{:.2f}€_".format(drink['name'], float(drink['price']))

    bot.sendMessage(chat_id=update.message.chat_id, text=output, parse_mode=ParseMode.MARKDOWN, reply_markup=kb_markup)

def commandBuy(bot, update): # Display available drinks as buttons and charge user accordingly
    mete_id = getMeteID(update.message.chat_id)
    if mete_id is None:
        output = "You are not linked to a mete account!"
        bot.sendMessage(chat_id=update.message.chat_id, text=output, reply_markup=kb_helponly_markup)
    else:
        drink_list = json.loads(requests.get(f"http://{BASE_ADDRESS}/api/v1/drinks.json").text)
        kb_drinks = list()

        output = "Please choose a drink from the list below:\n"
        n = int(len(drink_list)/3) + 1
        for i in range(n+1):
            column_drinks = list()
            for drink in drink_list[i*3:(i+1)*3]:
                drink_details = "{}: {:.2f}€".format(drink['name'], float(drink['price']))
                column_drinks.append(KeyboardButton(drink_details))
            kb_drinks.append(column_drinks)
        kb_drinks.append([KeyboardButton("/cancel")])
        kb_drinks_markup = ReplyKeyboardMarkup(kb_drinks)
        bot.sendMessage(chat_id=update.message.chat_id, text=output, reply_markup=kb_drinks_markup)

def commandBalance(bot, update): # Display current balance of user
    mete_id = getMeteID(update.message.chat_id)
    if mete_id is None:
        output = "You are not linked to a mete account!"
        bot.sendMessage(chat_id=update.message.chat_id, text=output, reply_markup=kb_helponly_markup)
    else:
        balance = getBalance(mete_id)
        output = "Your balance is _{:.2f}€_".format(balance)
        bot.sendMessage(chat_id=update.message.chat_id, text=output, reply_markup=kb_markup, parse_mode=ParseMode.MARKDOWN)

def commandCancel(bot, update):
    mete_id = getMeteID(update.message.chat_id)
    if mete_id is None:
        output = "You are not linked to a mete account!"
        bot.sendMessage(chat_id=update.message.chat_id, text=output, reply_markup=kb_helponly_markup)
    else:
        output = "This request has been cancelled."
        bot.sendMessage(chat_id=update.message.chat_id, text=output, reply_markup=kb_markup)

def handle_inlinerequest(bot, update): # Check request for account linking and act accordingly
    query = update.inline_query
    sender_id = query.from_user.id
    database = sqlite3.connect("user_data")
    cursor = database.cursor()

    cursor.execute('''SELECT admin FROM users WHERE telegram_id=?''', (sender_id,))
    isAdmin = cursor.fetchone()

    if isAdmin is None:
        return

    isAdmin = isAdmin[0]

    if not isAdmin:
        return

    results = list()
    input = query.query.split(" ")
    if input[0] == "link":
        mete_id = int(input[1])
        mete_user_list = json.loads(requests.get(f"http://{BASE_ADDRESS}/api/v1/users.json").text)

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
            return
        database.commit()
        cursor.close()

        output = "Press 'Link accounts' to link your Telegram account to the Mete account *{}*_(id: {})_.".format(mete_name, mete_id)
        kb_link = [[InlineKeyboardButton("Link accounts", callback_data="link/" + str(mete_id))], [InlineKeyboardButton("Cancel", callback_data="cancel")]]
        kb_link_markup = InlineKeyboardMarkup(kb_link)

        results.append(InlineQueryResultArticle(id="0", title="Send link request", input_message_content=InputTextMessageContent(output, parse_mode=ParseMode.MARKDOWN), reply_markup=kb_link_markup))
    elif input[0] == "promote":
        output = "Press 'Become administrator' to become a Chaosdorf-Mete administrator."
        kb_admin_requests = [[InlineKeyboardButton("Become administrator", callback_data="promote")], [InlineKeyboardButton("Cancel", callback_data="cancel")]]
        kb_admin_requests_markup = InlineKeyboardMarkup(kb_admin_requests)
        cursor.close()

        results.append(InlineQueryResultArticle(id="0", title="Send promotion request", input_message_content=InputTextMessageContent(output), reply_markup=kb_admin_requests_markup))
    bot.answer_inline_query(query.id, results)

def handle_buttonpress(bot, update): # Handle any inline buttonpresses related to this bot
    query = update.callback_query
    data = query.data.split("/")
    if data[0] == "link": # Confirm the linking of Telegram and Mete accounts
        mete_id = int(data[1])
        telegram_id = query.from_user.id

        database = sqlite3.connect("user_data")
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
    elif data[0] == "promote":
        a = 0
        abort = False
        user = query.from_user
        telegram_id = user.id
        mete_id = getMeteID(telegram_id)
        if mete_id is None:
            output = "*ERROR*: This user is not linked to Mete!"
            answer = "Error!"
        else:
            database = sqlite3.connect("user_data")
            cursor = database.cursor()

            cursor.execute('''SELECT admin FROM users WHERE telegram_id=?''', (telegram_id,))
            isAdmin = cursor.fetchone()[0]
            if isAdmin:
                output = "*ERROR*: This user is already an administrator!"
                answer = "Error!"
                abort = True
            if not abort:
                user_handle = user.username
                cursor.execute('''UPDATE users SET admin=1 WHERE telegram_id=?''', (telegram_id,))
                cursor.execute('''UPDATE users SET user_handle=? WHERE telegram_id=?''', (user_handle, telegram_id,))
                database.commit()
                cursor.close()

                output = "Successfully promoted this user to administrator!"
                output = "Success!"
    elif data[0] == "cancel":
        output = "This request has been cancelled."
        answer = "Cancelled!"
    bot.edit_message_text(output, inline_message_id=query.inline_message_id, parse_mode=ParseMode.MARKDOWN)
    bot.answer_callback_query(query.id, text=answer)

def handle_textinput(bot, update):
    mete_id = getMeteID(update.message.chat_id)
    if mete_id is None:
        output = "You are not linked to a mete account!"
        bot.sendMessage(chat_id=update.message.chat_id, text=output, reply_markup=kb_helponly_markup, parse_mode=ParseMode.MARKDOWN)
        return
    input = update.message.text
    splitup_input = input.split(":")
    if len(splitup_input) == 2:
        name, price = splitup_input[0], splitup_input[1][1:-1]
        abort = True
        drink_list = json.loads(requests.get(f"http://{BASE_ADDRESS}/api/v1/drinks.json").text)

        for drink in drink_list:
            if name == drink['name'] and price == "{:.2f}".format(float(drink['price'])):
                drink_id = drink['id']
                abort = False
                break
        if not abort:
            requests.get("http://{}/api/v1/users/{}/buy?drink={}".format(BASE_ADDRESS, mete_id, drink_id))
            output = "You purchased _{}_. Your new balance is _{:.2f}€_".format(name, getBalance(mete_id))
            bot.sendMessage(chat_id=update.message.chat_id, text=output, reply_markup=kb_markup, parse_mode=ParseMode.MARKDOWN)
            return
    output = "Your input confused me. Get some /help"
    bot.sendMessage(chat_id=update.message.chat_id, text=output, reply_markup=kb_markup, parse_mode=ParseMode.MARKDOWN)

def getMeteID(telegram_id):
    database = sqlite3.connect("user_data")
    cursor = database.cursor()

    cursor.execute('''SELECT mete_id FROM users WHERE telegram_id=?''', (telegram_id,))
    mete_id = cursor.fetchone()
    if mete_id is None:
        return None
    else:
        return mete_id[0]

def getBalance(mete_id):
    mete_user_list = json.loads(requests.get(f"http://{BASE_ADDRESS}/api/v1/users.json").text)
    for user in mete_user_list:
        if user['id'] == mete_id:
            balance = float(user['balance'])
            break
    return balance

dispatcher.add_handler(CommandHandler('start', commandStart))
dispatcher.add_handler(CommandHandler('help', commandStart))
dispatcher.add_handler(CommandHandler('list', commandList))
dispatcher.add_handler(CommandHandler('buy', commandBuy))
dispatcher.add_handler(CommandHandler('balance', commandBalance))
dispatcher.add_handler(CommandHandler('cancel', commandCancel))
dispatcher.add_handler(InlineQueryHandler(handle_inlinerequest))
dispatcher.add_handler(CallbackQueryHandler(handle_buttonpress))
dispatcher.add_handler(MessageHandler(Filters.text, handle_textinput))

updater.start_polling()

updater.idle()

database.close()
