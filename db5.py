from pymongo import MongoClient
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai
from datetime import datetime, timezone
import requests  # For making HTTP requests to the web search API

# MongoDB Connection
client = MongoClient("mongodb+srv://hbharambe71:Hemant87677@cluster0.m5zvr.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
db = client["telegram_bot"]
users = db["users"]
chat_history = db["chat_history"]
file_metadata = db["file_metadata"]  # New collection for file metadata

# Gemini API Key Configuration
GEN_API_KEY = "AIzaSyDfHHLZdrXa4ZO_1MGIqnGOm8QJusHnzjc"  # Replace with your Gemini API key
genai.configure(api_key=GEN_API_KEY)

# Web Search API Configuration
WEB_SEARCH_API_KEY = "24656b90917097c1409345ab1cbeca5c390f891b44bf1987c5efa2dcaedd79d7"  # Replace with your web search API key
WEB_SEARCH_API_URL = "https://serpapi.com/search"  # Example: SerpAPI endpoint

# Start Command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    existing_user = users.find_one({"chat_id": user.id})

    if existing_user:
        await update.message.reply_text(f"👋 Welcome back, {user.first_name}!")
    else:
        keyboard = [[KeyboardButton("📱 Share Contact", request_contact=True)]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text("Welcome! Please share your phone number using the button below.",
                                        reply_markup=reply_markup)

# Handle Contact Sharing
async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    contact = update.message.contact

    if contact.user_id != user.id:
        await update.message.reply_text("❌ Please share your own contact number.")
        return

    # Save user data to MongoDB
    user_data = {
        "first_name": user.first_name,
        "username": user.username,
        "chat_id": user.id,
        "phone_number": contact.phone_number
    }

    users.update_one({"chat_id": user.id}, {"$set": user_data}, upsert=True)
    await update.message.reply_text(f"✅ Thank you, {user.first_name}! Your phone number has been saved.")

# Gemini Chat Function
async def gemini_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    user = update.message.from_user
    chat_id = user.id

    try:
        # Fetch AI Response
        model = genai.GenerativeModel("gemini-pro")
        response = model.generate_content(user_message)

        # Extract text response properly
        if response.candidates and response.candidates[0].content.parts:
            bot_reply = response.candidates[0].content.parts[0].text.strip()
        else:
            bot_reply = "⚠️ Sorry, I couldn't generate a response."

        # Store chat history in MongoDB
        chat_data = {
            "chat_id": chat_id,
            "username": user.username,
            "first_name": user.first_name,
            "user_message": user_message,
            "bot_response": bot_reply,
            "timestamp": datetime.now(timezone.utc)  # Timezone-aware datetime
        }
        chat_history.insert_one(chat_data)

        # Send AI Response
        await update.message.reply_text(bot_reply)

    except Exception as e:
        await update.message.reply_text("⚠️ Sorry, an error occurred while processing your request.")
        print(f"Error: {e}")

# Web Search Function
async def web_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    chat_id = user.id
    query = " ".join(context.args)  # Extract the search query from the command

    if not query:
        await update.message.reply_text("Please provide a search query. Usage: /websearch <query>")
        return

    try:
        # Perform a web search using the API
        params = {
            "q": query,
            "api_key": WEB_SEARCH_API_KEY  # Add other required parameters for the API
        }
        response = requests.get(WEB_SEARCH_API_URL, params=params)
        search_results = response.json()

        # Extract top search results
        top_results = search_results.get("organic_results", [])[:5]  # Get top 5 results
        if not top_results:
            await update.message.reply_text("⚠️ No results found for your query.")
            return

        # Format the results for the user
        result_summary = f"🔍 Web Search Results for '{query}':\n\n"
        for i, result in enumerate(top_results, 1):
            result_summary += f"{i}. {result['title']}\n{result['link']}\n\n"

        # Use Gemini to summarize the results
        model = genai.GenerativeModel("gemini-pro")
        summary_prompt = f"Summarize the following web search results in 2-3 sentences:\n\n{result_summary}"
        summary_response = model.generate_content(summary_prompt)

        if summary_response.candidates and summary_response.candidates[0].content.parts:
            summary = summary_response.candidates[0].content.parts[0].text.strip()
        else:
            summary = "⚠️ Sorry, I couldn't generate a summary."

        # Send the summary and top links to the user
        await update.message.reply_text(f"📝 Summary:\n{summary}\n\n🔗 Top Links:\n{result_summary}")

    except Exception as e:
        await update.message.reply_text("⚠️ Sorry, an error occurred while performing the web search.")
        print(f"Error: {e}")

# Handle Image/File Analysis
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    chat_id = user.id
    file = update.message.document or update.message.photo[-1]  # Get the document or the last photo

    try:
        # Download the file
        file_path = await file.get_file().download()

        # Analyze the file content using Gemini
        model = genai.GenerativeModel("gemini-pro")
        analysis_response = model.generate_content(f"Describe the content of this file: {file.file_name}")

        # Extract analysis response
        if analysis_response.candidates and analysis_response.candidates[0].content.parts:
            analysis_result = analysis_response.candidates[0].content.parts[0].text.strip()
        else:
            analysis_result = "⚠️ Sorry, I couldn't analyze the file."

        # Save file metadata in MongoDB
        file_data = {
            "chat_id": chat_id,
            "file_name": file.file_name,
            "file_size": file.file_size,
            "file_type": file.mime_type,
            "analysis": analysis_result,
            "timestamp": datetime.now(timezone.utc)
        }
        file_metadata.insert_one(file_data)

        # Send analysis result
        await update.message.reply_text(analysis_result)

    except Exception as e:
        await update.message.reply_text("⚠️ Sorry, an error occurred while processing your file.")
        print(f"Error in handle_file: {e}")

# Main Function to Run the Bot
if __name__ == "__main__":
    bot_token = "7971814599:AAFIuuOB_S7gQD8qcffSC9eH_ISLfpooIyc"  # Replace with your Telegram Bot token
    app = ApplicationBuilder().token(bot_token).build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, gemini_chat))  # AI Chat
    app.add_handler(CommandHandler("websearch", web_search))  # Web Search
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))  # Handle files and images

    # Start the bot
    print("🤖 Bot is running...")
    app.run_polling()