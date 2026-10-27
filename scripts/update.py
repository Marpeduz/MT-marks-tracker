import os
import json
from datetime import datetime
import urllib.request
import urllib.error

# Эндпоинты Poliroid для RU-кластера Lesta («Мир Танков»)
VEHICLES_URL = "https://poliroid.me/gunmarks/api/v2/vehicles/ru/ru"
MARKS_URL = "https://poliroid.me/gunmarks/api/v2/data/ru/vehicles/65,85,95,100"

DATA_DIR = "data"
HISTORY_DIR = os.path.join(DATA_DIR, "history")

def fetch_json(url):
    """Безопасная загрузка JSON по URL с заголовком браузера"""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as e:
        print(f"❌ Ошибка запроса к {url}: {e}")
        return None

def main():
    print("🚀 Запуск обновления данных отметок...")

    # Создаем папки, если их нет
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(HISTORY_DIR, exist_ok=True)

    # 1. Загружаем справочник техники
    vehicles_data = fetch_json(VEHICLES_URL)
    if not vehicles_data or vehicles_data.get("status") != "ok":
        raise Exception("Не удалось загрузить справочник техники!")

    meta = vehicles_data["data"]["meta"]
    raw_vehicles = vehicles_data["data"]["data"]["vehicles"]
    
    # Индексы полей в массиве техники Poliroid:
    # 0: id, 1: tag, 2: nation, 3: type, 4: tier, 5: name, 6: short_name, 
    # 8: is_premium, 9: is_special, 10: is_collector, 11: tankopedia, 12: role
    vehicles_map = {}
    for v in raw_vehicles:
        tank_id = v[0]
        tier = v[4]
        tankopedia_flag = v[11]
        
        # Фильтруем: только уровни 5–11 и реальная техника (tankopedia == 1)
        if 5 <= tier <= 11 and tankopedia_flag == 1:
            vehicles_map[tank_id] = {
                "id": tank_id,
                "tag": v[1],
                "nation": v[2],
                "type": v[3],
                "tier": tier,
                "name": v[5],
                "short_name": v[6],
                "is_premium": bool(v[8]),
                "is_special": bool(v[9]),
                "is_collector": bool(v[10]),
                "role": v[12] if len(v) > 12 else ""
            }

    print(f"Фильтры применились: {len(vehicles_map)} танков V-XI уровней найдено в базе.")

    # 2. Загружаем актуальные планки отметок (65, 85, 95, 100)
    marks_data = fetch_json(MARKS_URL)
    if not marks_data or marks_data.get("status") != "ok":
        raise Exception("Не удалось загрузить планки отметок!")

    raw_marks = marks_data["data"]["data"]
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    
    result_list = []
    updated_count = 0

    for item in raw_marks:
        tank_id = item["id"]
        if tank_id not in vehicles_map:
            continue
        
        marks = item.get("marks", {})
        m65 = marks.get("65")
        m85 = marks.get("85")
        m95 = marks.get("95")
        m100 = marks.get("100")

        # Базовая валидация логики порогов
        if m65 and m85 and m95:
            if not (m65 < m85 < m95):
                continue

        tank_info = vehicles_map[tank_id]
        tank_info["marks"] = {
            "65": m65,
            "85": m85,
            "95": m95,
            "100": m100
        }

        result_list.append(tank_info)
        updated_count += 1

        # Сохранение суточной истории для графиков
        history_file = os.path.join(HISTORY_DIR, f"{tank_id}.json")
        history_data = []
        if os.path.exists(history_file):
            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    history_data = json.load(f)
            except:
                history_data = []

        if not history_data or history_data[-1].get("date") != today_str:
            history_data.append({
                "date": today_str,
                "65": m65,
                "85": m85,
                "95": m95,
                "100": m100
            })
            if len(history_data) > 365:
                history_data = history_data[-365:]

            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(history_data, f, ensure_ascii=False)

    if updated_count < 400:
        raise Exception(f"Критическая ошибка: получено слишком мало танков ({updated_count}), обновление отменяется!")

    # 3. Сохраняем финальный latest.json для сайта
    output_data = {
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "version": meta.get("version", 1),
        "icons_url": meta.get("icons_url", ""),
        "vehicles": result_list
    }

    latest_path = os.path.join(DATA_DIR, "latest.json")
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, separators=(',', ':'))

    print(f"Успешно! Обновлено танков: {updated_count}. Файл {latest_path} сохранен.")

if __name__ == "__main__":
    main()
