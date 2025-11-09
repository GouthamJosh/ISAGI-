# CREDITS TO @CyberTGX

import asyncio
from pyrogram import Client, idle, __version__
from pyrogram.raw.all import layer
from aiohttp import web
from mfinder import APP_ID, API_HASH, BOT_TOKEN 

try:
    from database.mongo import start_mongo
except ImportError:
    print("Warning: Could not import start_mongo. Database connection must be handled manually.")
    start_mongo = lambda: None

routes = web.RouteTableDef()

@routes.get("/", allow_head=True)
async def root_route_handler(request):
    """Simple health check route."""
    return web.json_response({"status": "CyberTG Bot is running"})

async def web_server():
    """Initializes and configures the AIOHTTP web application."""
    web_app = web.Application(client_max_size=30000000)
    web_app.add_routes(routes)
    return web_app

async def main():
    print("Starting MongoDB connection...")
    try:
        start_mongo()
        print("MongoDB connection successful.")
    except Exception as e:
        print(f"FATAL ERROR: Failed to connect to MongoDB. Shutting down. Error: {e}")
        return

    plugins = dict(root="mfinder/plugins")
    app = Client(
        name="mfinder",
        api_id=APP_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
        plugins=plugins,
    )

    async with app:
        me = await app.get_me()
        print(
            f"{me.first_name} - @{me.username} - Pyrogram v{__version__} (Layer {layer}) - Started..."
        )

        try:
            web_runner = web.AppRunner(await web_server())
            await web_runner.setup()
            bind_address = "0.0.0.0"
            await web.TCPSite(web_runner, bind_address, 8080).start()
            print(f"Web server started and listening on http://{bind_address}:8080")
        except Exception as e:
            print(f"ERROR: Failed to start web server. {e}")

        await idle()

        print(f"{me.first_name} - @{me.username} - Stopped !!!")
        
asyncio.run(main())
