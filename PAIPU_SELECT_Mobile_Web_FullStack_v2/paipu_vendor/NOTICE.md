# Third-party code

The mahjong_url_parser subset is from LekangZou/Mahjong-Replay-Converter,
MIT licensed, commit 61f5ae1f36ee7419173cccb03fe8afdf81d57e28.
The package initializer is reduced to avoid importing its desktop application.
The application uses its replay URL parser, data models, SDK session model,
Tenhou validation and record conversion helpers. Its game authentication and
bootstrap functions are not used. Authentication is in regional_auth.py and
majsoul_client.py. No Soulless implementation source is included.

Protocol facts and the version mapping were compared with Soulless 0.3.2,
commit 933a9dd34b8041123007c5b9be70bd95826e70cf, and soulless_proto 0.11.612.
