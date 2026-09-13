# Vaqtincha test uchun: Birinchi kelgan 1 ta e'lonni majburiy yuborish
if scraped_items:
    test_item = scraped_items[0]
    send_telegram_message(test_item)
    print(f"Test e'lon yuborildi: {test_item.get('id')}")
