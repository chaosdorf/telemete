from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, InlineQueryHandler, CallbackQueryHandler
from telegram import InlineQueryResultArticle, InputTextMessageContent, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, ParseMode
from valuables import API_KEY, BASE_ADDRESS, INIT_ADMIN
import requests
import json
import sqlite3

updater = Updater(token=API_KEY)
dispatcher = updater.dispatcher
database = sqlite3.connect("user_data")
cursor = database.cursor()

cursor.execute('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, telegram_id INTEGER, mete_id INTEGER, admin INTEGER DEFAULT 0)''')
cursor.execute('''SELECT id FROM users WHERE telegram_id=?''', (INIT_ADMIN['telegram_id'],))
if cursor.fetchone() is None:
    cursor.execute('''INSERT INTO users(telegram_id, mete_id, admin) VALUES(?,?,?)''', (INIT_ADMIN['telegram_id'], INIT_ADMIN['mete_id'], 1,))
database.commit()
cursor.close()

kb = [[KeyboardButton("/list"), KeyboardButton("/buy"), KeyboardButton("/balance"), KeyboardButton("/help")]]

kb_markup = ReplyKeyboardMarkup(kb, resize_keyboard=True)

def commandStart(bot, update): # Startup and help message
    bot.sendMessage(chat_id=update.message.chat_id, text="We are online!", reply_markup=kb_markup)

def commandList(bot, update): # Display available drinks
    drink_list = json.loads(requests.get(f"http://{BASE_ADDRESS}/api/v1/drinks.json").text)

    output = "Available drinks:\n"

    for drink in drink_list:
        output += "\n{}: _{}€_".format(drink['name'], drink['price'])

    bot.sendMessage(chat_id=update.message.chat_id, text=output, parse_mode=ParseMode.MARKDOWN, reply_markup=kb_markup)

def commandBuy(bot, update): # Display available drinks as buttons and charge user accordingly
    bot.sendMessage(chat_id=update.message.chat_id, text="We are online!", reply_markup=kb_markup)

def commandBalance(bot, update): # Display current balance of user
    bot.sendMessage(chat_id=update.message.chat_id, text="We are online!", reply_markup=kb_markup)

def request_link(bot, update): # Check request for account linking and act accordingly
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
        print("{} requested a link, but the user isn't an admin".format(sender_id))
        return

    results = list()
    mete_id = int(query.query)
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
    kb_link = [[InlineKeyboardButton("Link accounts", callback_data="link/" + str(mete_id))], [InlineKeyboardButton("Cancel", callback_data="cancel/")]]
    kb_link_markup = InlineKeyboardMarkup(kb_link)

    results.append(InlineQueryResultArticle(id="0", title="Send link request", input_message_content=InputTextMessageContent(output, parse_mode=ParseMode.MARKDOWN), reply_markup=kb_link_markup))

    bot.answer_inline_query(query.id, results)

def confirm_link(bot, update): # Confirm the linking of Telegram and Mete accounts
    query = update.callback_query
    print(query)
    if query.data == "cancel":
        output = "This request has been canceled."
        answer = "Canceled!"
    else:
        data = query.data.split("/")
        print("lel")
        mete_id = int(data[1])
        print(mete_id)
        telegram_id = query.from_user.id

        database = sqlite3.connect("user_data")
        cursor = database.cursor()
        cursor.execute('''SELECT id FROM users WHERE telegram_id=?''', (telegram_id,))
        if not (cursor.fetchone() is None):
            output = "*ERROR*: This user is already linked to Mete!"
            answer = "Error!"
        else:
            cursor.execute('''INSERT INTO users(telegram_id, mete_id) VALUES(?,?)''', (telegram_id, mete_id,))
            output = "Successfully connected this user to Mete!"
            answer = "Success!"
            print("Linked {} to {}!".format(telegram_id, mete_id))
    database.commit()
    cursor.close()

    bot.edit_message_text(output, inline_message_id=query.inline_message_id, parse_mode=ParseMode.MARKDOWN)
    bot.answer_callback_query(query.id, text=answer)

dispatcher.add_handler(CommandHandler('start', commandStart))
dispatcher.add_handler(CommandHandler('help', commandStart))
dispatcher.add_handler(CommandHandler('list', commandList))
dispatcher.add_handler(CommandHandler('buy', commandBuy))
dispatcher.add_handler(CommandHandler('balance', commandBalance))
dispatcher.add_handler(InlineQueryHandler(request_link))
dispatcher.add_handler(CallbackQueryHandler(confirm_link))

updater.start_polling()

updater.idle()

database.close()
