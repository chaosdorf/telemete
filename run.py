from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, InlineQueryHandler, CallbackQueryHandler
from telegram import InlineQueryResultArticle, InputTextMessageContent, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from valuables import API_KEY, BASE_ADDRESS

updater = Updater(token=API_KEY)
dispatcher = updater.dispatcher

def commandStart(bot, update): # Startup and help message
    bot.sendMessage(chat_id=update.message.chat_id, text="We are online!")

def commandList(bot, update): # Display available drinks
    bot.sendMessage(chat_id=update.message.chat_id, text="We are online!")

def commandBuy(bot, update): # Display available drinks as buttons and charge user accordingly
    bot.sendMessage(chat_id=update.message.chat_id, text="We are online!")

def commandBalance(bot, update): # Display current balance of user
    bot.sendMessage(chat_id=update.message.chat_id, text="We are online!")

dispatcher.add_handler(CommandHandler('start', commandStart))
dispatcher.add_handler(CommandHandler('help', commandStart))
dispatcher.add_handler(CommandHandler('list', commandList))
dispatcher.add_handler(CommandHandler('buy', commandBuy))
dispatcher.add_handler(CommandHandler('balance', commandBalance))

updater.start_polling()

updater.idle()
