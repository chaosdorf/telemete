from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, InlineQueryHandler, CallbackQueryHandler
from telegram import InlineQueryResultArticle, InputTextMessageContent, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from valuables import API_KEY, BASE_ADDRESS

updater = Updater(token=API_KEY)
dispatcher = updater.dispatcher



updater.start_polling()

updater.idle()
